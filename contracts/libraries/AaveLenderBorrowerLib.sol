// SPDX-License-Identifier: agpl-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

import "./SupportStructs.sol";
import "./aave/DataTypes.sol";
import "../interfaces/aave/IReserveInterestRateStrategy.sol";
import "../interfaces/aave/ILendingPool.sol";
import "../interfaces/aave/IStakedAave.sol";
import "../interfaces/aave/IPriceOracle.sol";
import "../interfaces/aave/IAToken.sol";
import "../interfaces/aave/IVariableDebtToken.sol";
import "../interfaces/IOptionalERC20.sol";

import "../interfaces/aave/IProtocolDataProvider.sol";
import "@openzeppelin/contracts/math/SafeMath.sol";
import "../WadRayMath.sol";

library AaveLenderBorrowerLib {
    using SafeMath for uint256;
    using WadRayMath for uint256;

    function protocolDataProvider()
        public
        view
        returns (IProtocolDataProvider)
    {
        return
            IProtocolDataProvider(0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d);
    }

    function lendingPool() public view returns (ILendingPool) {
        return
            ILendingPool(
                protocolDataProvider().ADDRESSES_PROVIDER().getLendingPool()
            );
    }

    function priceOracle() public view returns (IPriceOracle) {
        return
            IPriceOracle(
                protocolDataProvider().ADDRESSES_PROVIDER().getPriceOracle()
            );
    }

    function incentivesController(
        IAToken aToken,
        IVariableDebtToken variableDebtToken,
        bool isWantIncentivised,
        bool isInvestmentTokenIncentivised
    ) public view returns (IAaveIncentivesController) {
        if (isWantIncentivised) {
            return aToken.getIncentivesController();
        } else if (isInvestmentTokenIncentivised) {
            return variableDebtToken.getIncentivesController();
        } else {
            return IAaveIncentivesController(0);
        }
    }

    function toETH(uint256 _amount, address asset)
        public
        view
        returns (uint256)
    {
        return
            _amount.mul(priceOracle().getAssetPrice(asset)).div(
                uint256(10)**uint256(IOptionalERC20(asset).decimals())
            );
    }

    function fromETH(uint256 _amount, address asset)
        public
        view
        returns (uint256)
    {
        return
            _amount
                .mul(uint256(10)**uint256(IOptionalERC20(asset).decimals()))
                .div(priceOracle().getAssetPrice(asset));
    }

    function calcMaxDebt(
        ILendingPool _lendingPool,
        IProtocolDataProvider _pdp,
        address _investmentToken,
        uint256 _acceptableCostsRay
    )
        external
        view
        returns (uint256 currentProtocolDebt, uint256 maxProtocolDebt)
    {
        // This function is used to calculate the maximum amount of debt that the protocol can take
        // to keep the cost of capital lower than the set acceptableCosts
        // This maxProtocolDebt will be used to decide if capital costs are acceptable or not
        // and to repay required debt to keep the rates below acceptable costs

        // Hack to avoid the stack too deep compiler error.
        SupportStructs.CalcMaxDebtLocalVars memory vars;
        DataTypes.ReserveData memory reserveData =
            _lendingPool.getReserveData(address(_investmentToken));
        IReserveInterestRateStrategy irs =
            IReserveInterestRateStrategy(
                reserveData.interestRateStrategyAddress
            );

        (
            vars.availableLiquidity, // = total supply - total stable debt - total variable debt
            vars.totalStableDebt, // total debt paying stable interest rates
            vars.totalVariableDebt, // total debt paying stable variable rates
            ,
            ,
            ,
            ,
            ,
            ,

        ) = protocolDataProvider().getReserveData(address(_investmentToken));

        vars.totalDebt = vars.totalStableDebt.add(vars.totalVariableDebt);
        vars.totalLiquidity = vars.availableLiquidity.add(vars.totalDebt);
        vars.utilizationRate = vars.totalDebt == 0
            ? 0
            : vars.totalDebt.rayDiv(vars.totalLiquidity);

        // Aave's Interest Rate Strategy Parameters (see docs)
        SupportStructs.IrsVars memory irsVars;
        irsVars.optimalRate = irs.OPTIMAL_UTILIZATION_RATE();
        irsVars.baseRate = irs.baseVariableBorrowRate(); // minimum cost of capital with 0 % of utilisation rate
        irsVars.slope1 = irs.variableRateSlope1(); // rate of increase of cost of debt up to Optimal Utilisation Rate
        irsVars.slope2 = irs.variableRateSlope2(); // rate of increase of cost of debt above Optimal Utilisation Rate

        // acceptableCosts should always be > baseVariableBorrowRate
        // If it's not this will revert since the strategist set the wrong
        // acceptableCosts value
        if (
            vars.utilizationRate < irsVars.optimalRate &&
            _acceptableCostsRay < irsVars.baseRate.add(irsVars.slope1)
        ) {
            // we solve Aave's Interest Rates equation for sub optimal utilisation rates
            // IR = BASERATE + SLOPE1 * CURRENT_UTIL_RATE / OPTIMAL_UTIL_RATE
            vars.targetUtilizationRate = (
                _acceptableCostsRay.sub(irsVars.baseRate)
            )
                .rayMul(irsVars.optimalRate)
                .rayDiv(irsVars.slope1);
        } else {
            // Special case where protocol is above utilization rate but we want
            // a lower interest rate than (base + slope1)
            if (_acceptableCostsRay < irsVars.baseRate.add(irsVars.slope1)) {
                return (toETH(vars.totalDebt, address(_investmentToken)), 0);
            }

            // we solve Aave's Interest Rates equation for utilisation rates above optimal U
            // IR = BASERATE + SLOPE1 + SLOPE2 * (CURRENT_UTIL_RATE - OPTIMAL_UTIL_RATE) / (1-OPTIMAL_UTIL_RATE)
            vars.targetUtilizationRate = (
                _acceptableCostsRay.sub(irsVars.baseRate.add(irsVars.slope1))
            )
                .rayMul(uint256(1e27).sub(irsVars.optimalRate))
                .rayDiv(irsVars.slope2)
                .add(irsVars.optimalRate);
        }

        vars.maxProtocolDebt = vars
            .totalLiquidity
            .rayMul(vars.targetUtilizationRate)
            .rayDiv(1e27);

        return (
            toETH(vars.totalDebt, address(_investmentToken)),
            toETH(vars.maxProtocolDebt, address(_investmentToken))
        );
    }

    function checkCooldown(
        bool isWantIncentivised,
        bool isInvestmentTokenIncentivised,
        address stkAave
    ) external view returns (bool) {
        if (!isWantIncentivised && !isInvestmentTokenIncentivised) {
            return false;
        }

        uint256 cooldownStartTimestamp =
            IStakedAave(stkAave).stakersCooldowns(address(this));
        uint256 COOLDOWN_SECONDS = IStakedAave(stkAave).COOLDOWN_SECONDS();
        uint256 UNSTAKE_WINDOW = IStakedAave(stkAave).UNSTAKE_WINDOW();
        return
            cooldownStartTimestamp != 0 &&
            block.timestamp > cooldownStartTimestamp.add(COOLDOWN_SECONDS) &&
            block.timestamp <=
            cooldownStartTimestamp.add(COOLDOWN_SECONDS).add(UNSTAKE_WINDOW);
    }
}
