// SPDX-License-Identifier: AGPL-3.0
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

import {BaseStrategy} from "@yearnvaults/contracts/BaseStrategy.sol";
import "@openzeppelin/contracts/math/Math.sol";

import {
    SafeERC20,
    SafeMath,
    IERC20,
    Address
} from "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";
import "./WadRayMath.sol";

import "./interfaces/IOptionalERC20.sol";
import "./interfaces/ISwap.sol";
import "./interfaces/IWETH.sol";
import "./interfaces/IVault.sol";
import "./interfaces/aave/IAToken.sol";
import "./interfaces/aave/IStakedAave.sol";
import "./interfaces/aave/ILendingPool.sol";
import "./interfaces/aave/IVariableDebtToken.sol";
import "./interfaces/aave/IProtocolDataProvider.sol";
import "./interfaces/aave/IAaveIncentivesController.sol";
import "./interfaces/aave/ILendingPoolAddressesProvider.sol";
import "./interfaces/aave/IReserveInterestRateStrategy.sol";

contract Strategy is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;
    using WadRayMath for uint256;

    ISwap public constant sushiswap =
        ISwap(address(0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F));
    ISwap public constant uniswap =
        ISwap(address(0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D));
    ISwap public router =
        ISwap(address(0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D));

    IStakedAave public constant stkAave =
        IStakedAave(0x4da27a545c0c5B758a6BA100e3a049001de870f5);
    IProtocolDataProvider public constant protocolDataProvider =
        IProtocolDataProvider(
            address(0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d)
        );
    IAToken public aToken;
    IVault public yVault;
    IERC20 public investmentToken;
    IVariableDebtToken public variableDebtToken;
    address public constant WETH =
        address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    address public constant AAVE =
        address(0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9);

    // true if this token is incentivised
    bool public isIncentivised;

    // max interest rate we can afford to pay for borrowing investment token
    uint256 public acceptableCostsRay = 1e25; // 1% 

    // Aave's referral code
    uint16 internal referral;

    // NOTE: LTV = Loan-To-Value = debt/collateral
    // Target LTV: ratio up to which which we will borrow 
    uint256 public targetLTVMultiplier = 6_000; // 60% of liquidation LTV
    // Warning LTV: ratio at which we will repay 
    uint256 public warningLTVMultiplier = 8_000; // 80% of liquidation LTV

    uint256 internal constant MAX_BPS = 10_000; // 100%

    uint256 public maxTotalBorrowIT;

    constructor(
        address _vault,
        address _yVault,
        bool _isIncentivised
    ) public BaseStrategy(_vault) {
        // You can set these parameters on deployment to whatever you want
        // maxReportDelay = 6300;
        // profitFactor = 100;
        // debtThreshold = 0;
        yVault = IVault(_yVault);
        investmentToken = IERC20(IVault(_yVault).token());
        (address _aToken, , ) =
            protocolDataProvider.getReserveTokensAddresses(address(want));
        aToken = IAToken(_aToken);
        (, , address _variableDebtToken) =
            protocolDataProvider.getReserveTokensAddresses(
                address(investmentToken)
            );
        variableDebtToken = IVariableDebtToken(_variableDebtToken);

        isIncentivised = _isIncentivised;
        referral = 179;
        maxTotalBorrowIT = type(uint256).max;
    }

    // ----------------- PUBLIC VIEW FUNCTIONS -----------------

    function name() external view override returns (string memory) {
        string memory _want = IOptionalERC20(address(want)).symbol();
        string memory _lend = string(abi.encodePacked("Lend:", _want));
        string memory _investmentToken =
            IOptionalERC20(address(investmentToken)).symbol();
        string memory _borrow =
            string(abi.encodePacked("Borrow:", _investmentToken));
        return string(abi.encodePacked("StrategyAave ", _lend, " ", _borrow));
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        return
            balanceOfWant()
                .add(balanceOfAToken()) // asset suplied as collateral
                .add(_investmentTokenToWant(_valueOfInvestment())) // current value of assets deposited in vault
                .sub(_investmentTokenToWant(balanceOfDebt())); // liabilities
    }

    // ----------------- SETTERS -----------------
    // for the management to activate / deactivate incentives functionality
    function setIsIncentivised(bool _isIncentivised) external onlyAuthorized {
        // NOTE: if the aToken is not incentivised, getIncentivesController() might revert (aToken won't implement it)
        // to avoid calling it, we use the OR and lazy evaluation
        require(
            !_isIncentivised ||
                address(aToken.getIncentivesController()) != address(0),
            "!aToken does not have incentives controller set up"
        );
        isIncentivised = _isIncentivised;
    }

    function setMaxTotalBorrowIT(uint256 _maxTotalBorrowIT)
        external
        onlyAuthorized
    {
        maxTotalBorrowIT = _maxTotalBorrowIT;
    }

    function setReferralCode(uint16 _referral) external onlyAuthorized {
        require(_referral != 0, "!invalid referral code");
        referral = _referral;
    }

    function setTargetMultiplier(uint256 _multiplier) external onlyAuthorized {
        require(_multiplier < MAX_BPS && _multiplier < warningLTVMultiplier);
        warningLTVMultiplier = _multiplier;
    }

    function setWarningMultiplier(uint256 _multiplier) external onlyAuthorized {
        require(_multiplier < MAX_BPS && _multiplier > targetLTVMultiplier);
        warningLTVMultiplier = _multiplier;
    }

    function setInvestmentToken(address _setInvestmentToken) external onlyAuthorized {
        // TODO: retrieve and set vault 
        // TODO: retrieve and set variableDebtToken
        // TODO: set investmentToken
    }

    function setAcceptableCosts(uint256 _acceptableCostsRay)
        external
        onlyAuthorized
    {
        acceptableCostsRay = _acceptableCostsRay;
    }

    // ----------------- MAIN STRATEGY FUNCTIONS -----------------

    function prepareReturn(uint256 _debtOutstanding)
        internal
        override
        returns (
            uint256 _profit,
            uint256 _loss,
            uint256 _debtPayment
        )
    {

        uint256 balanceInit = balanceOfWant();
        // claim rewards from Aave's Liquidity Mining Program
        _claimRewards();
        // claim rewards from yVault
        _takeVaultProfit();

        // TODO: claim back earnings from lending interest rates

        uint256 balanceOfWant = balanceOfWant();
        if (balanceOfWant > balanceInit) {
            _profit = balanceOfWant.sub(balanceInit);
        }

        // if the vault is claiming repayment of debt
        if (_debtOutstanding > 0) {
            uint256 _amountFreed = 0;
            (_amountFreed, _loss) = liquidatePosition(_debtOutstanding);
            _debtPayment = Math.min(_debtOutstanding, _amountFreed);
            if (_loss > 0) {
                _profit = 0;
            }
        }
    }

    event Stats(
        uint256 totalCollateralETH,
        uint256 totalDebtETH,
        uint256 availableBorrowsETH,
        uint256 currentLiquidationThreshold,
        uint256 currentLTV,
        uint256 healthFactor
    );

    function adjustPosition(uint256 _debtOutstanding) internal override {

        uint256 wantBalance = balanceOfWant();

        // if we have enough want to deposit more into Aave, we do
        // NOTE: we do not skip the rest of the function if we don't as it may need to repay or take on more debt
        if (_debtOutstanding < wantBalance) {
            uint256 amountToDeposit = wantBalance.sub(_debtOutstanding);
            _depositToAave(amountToDeposit);
        }

        // NOTE: debt + collateral calcs are done in ETH
        (
            uint256 totalCollateralETH,
            uint256 totalDebtETH,
            uint256 availableBorrowsETH,
            uint256 currentLiquidationThreshold,
            uint256 ltv,
            uint256 healthFactor
        ) = _getAaveUserAccountData();

        uint256 currentLTV = totalDebtETH.mul(MAX_BPS).div(totalCollateralETH);
        uint256 targetLTV = _getTargetLTV(currentLiquidationThreshold); // 60% under liquidation Threshold
        uint256 warningLTV = _getWarningLTV(currentLiquidationThreshold); // 80% under liquidation Threshold
  
        // decide in which range we are and act accordingly:
        // SUBOPTIMAL(borrow) (e.g. from 0 to 60% liqLTV)
        // HEALTHY(do nothing) (e.g. from 60% to 80% liqLTV)
        // UNHEALTHY(repay) (e.g. from 80% to 100% liqLTV)

        // we use our target cost of capital to calculate how much debt we can take on / how much debt we need to repay
        // in order to bring costs back to an acceptable range
        // currentProtocolDebt => total amount of debt taken by all Aave's borrowers
        // maxProtocolDebt => amount of total debt at which the cost of capital is equal to our acceptable costs
        // if the current protocol debt is higher than the max protocol debt, we will repay debt
        (uint256 currentProtocolDebt, uint256 maxProtocolDebt) =
            _calculateMaxDebt();

        if (currentLTV < targetLTV && currentProtocolDebt < maxProtocolDebt) {
            // SUBOPTIMAL RATIO: our current Loan-to-Value is lower than what we want
            // AND costs are lower than our max acceptable costs

            // we need to take on more debt
            uint256 targetDebtETH =
                totalCollateralETH.mul(targetLTV).div(MAX_BPS);

            uint256 amountToBorrowETH = targetDebtETH.sub(totalDebtETH);
            amountToBorrowETH = Math.min(
                availableBorrowsETH,
                amountToBorrowETH
            );

            // cap the amount of debt we are taking according to our acceptable costs
            // if with the new loan we are increasing our cost of capital over what is healthy
            if (currentProtocolDebt.add(amountToBorrowETH) > maxProtocolDebt) {
                // Can't underflow because it's checked in the previous if condition
                amountToBorrowETH = maxProtocolDebt.sub(currentProtocolDebt);
            }

            uint256 maxTotalBorrowETH = _investmentTokenToETH(maxTotalBorrowIT);
            if(totalDebtETH.add(amountToBorrowETH) > maxTotalBorrowETH) {
                amountToBorrowETH = maxTotalBorrowETH > totalDebtETH ? maxTotalBorrowETH.sub(totalDebtETH) : 0;
            }

            // convert to InvestmentToken
            uint256 amountToBorrowIT = _ethToInvestmentToken(amountToBorrowETH);
            _borrowInvestmentToken(amountToBorrowIT);
            _depositInYVault();
        } else if (
            currentLTV > warningLTV || currentProtocolDebt > maxProtocolDebt
        ) {
            // UNHEALTHY RATIO
            // we may be in this case if the current cost of capital is higher than our max cost of capital
            // we repay debt to set it to targetLTV
            uint256 targetDebtETH =
                targetLTV.mul(totalCollateralETH).div(MAX_BPS);
            uint256 amountToRepayETH = totalDebtETH.sub(targetDebtETH);

            if(maxProtocolDebt == 0) {
                amountToRepayETH = totalDebtETH;    
            } else if (currentProtocolDebt > maxProtocolDebt) {
                amountToRepayETH = Math.max(
                    amountToRepayETH,
                    currentProtocolDebt - maxProtocolDebt 
                );
            }

            uint256 amountToRepayIT = _ethToInvestmentToken(amountToRepayETH);
            uint256 withdrawnIT = _withdrawFromYVault(amountToRepayIT); // we withdraw from investmentToken vault
            _repayInvestmentTokenDebt(withdrawnIT); // we repay the investmentToken debt with Aave
        }
    }

    function liquidatePosition(uint256 _amountNeeded)
        internal
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        uint256 balance = balanceOfWant();
        // if we have enough want to take care of the liquidatePosition without actually liquidating positons
        if (balance >= _amountNeeded) {
            return (_amountNeeded, 0);
        }

        // NOTE: amountNeeded is in want
        // NOTE: amountToWithdraw is in want.
        // NOTE: repayment amount is in investmentToken
        // NOTE: collateral and debt calcs are done in ETH

        uint256 amountToWithdraw = _amountNeeded.sub(balance);

        // it will return the free amount of want
        uint256 totalAssets = _withdrawFromAave(amountToWithdraw);
        if (_amountNeeded > totalAssets) {
            _liquidatedAmount = totalAssets;
            _loss = _amountNeeded.sub(totalAssets);
        } else {
            _liquidatedAmount = _amountNeeded;
        }
    }

    function _withdrawFromYVault(uint256 _amountIT) internal returns (uint256) {
        if (_amountIT == 0) {
            return 0;
        }
        // no need to check allowance bc the contract == token
        uint256 balancePrior = balanceOfInvestmentToken();
        uint256 sharesToWithdraw =
            Math.min(_investmentTokenToYShares(_amountIT), _balanceOfYShares());
        yVault.withdraw(sharesToWithdraw);
        return balanceOfInvestmentToken().sub(balancePrior);
    }

    // NOTE: Can override `tendTrigger` and `harvestTrigger` if necessary

    function prepareMigration(address _newStrategy) internal override {
        // TODO: Transfer any non-`want` tokens to the new strategy
        // NOTE: `migrate` will automatically forward all `want` in this strategy to the new one
        liquidatePosition(vault.strategies(address(this)).totalDebt);
    }

    // ----------------- EXTERNAL FUNCTIONS MANAGEMENT -----------------

    function startCooldown() external onlyAuthorized {
        // for emergency cases
        IStakedAave(stkAave).cooldown(); // it will revert if balance of stkAave == 0
    }

    struct CalcMaxDebtLocalVars {
        uint256 availableLiquidity;
        uint256 totalStableDebt;
        uint256 totalVariableDebt;
        uint256 totalDebt;
        uint256 utilizationRate;
        uint256 totalLiquidity;
        uint256 targetUtilizationRate;
        uint256 maxProtocolDebt;
    }

    struct IrsVars {
        uint256 optimalRate;
        uint256 baseRate;
        uint256 slope1;
        uint256 slope2;
    }

    // ----------------- INTERNAL FUNCTIONS SUPPORT -----------------
    function _calculateMaxDebt()
        internal
        returns (uint256 currentProtocolDebt, uint256 maxProtocolDebt)
    {
        // TODO: should we take into account rewards?

        // This function is used to calculate the maximum amount of debt that the protocol can take 
        // to keep the cost of capital lower than the set acceptableCosts
        // This maxProtocolDebt will be used to decide if capital costs are acceptable or not
        // and to repay required debt to keep the rates below acceptable costs

        // Hack to avoid the stack too deep compiler error.
        CalcMaxDebtLocalVars memory vars;
        vars.availableLiquidity = 0;
        vars.totalStableDebt = 0;
        vars.totalVariableDebt = 0;
        vars.totalDebt = 0;
        vars.utilizationRate = 0;
        vars.totalLiquidity = 0;
        vars.targetUtilizationRate = 0;
        vars.maxProtocolDebt = 0;

        DataTypes.ReserveData memory reserveData =
            _lendingPool().getReserveData(address(investmentToken));
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

        ) = protocolDataProvider.getReserveData(address(investmentToken));

        vars.totalDebt = vars.totalStableDebt.add(vars.totalVariableDebt);
        vars.totalLiquidity = vars.availableLiquidity.add(vars.totalDebt);
        vars.utilizationRate = vars.totalDebt == 0
            ? 0
            : vars.totalDebt.rayDiv(
                vars.totalLiquidity
            );

        // Aave's Interest Rate Strategy Parameters (see docs)
        IrsVars memory irsVars;
        irsVars.optimalRate = irs.OPTIMAL_UTILIZATION_RATE(); 
        irsVars.baseRate = irs.baseVariableBorrowRate(); // minimum cost of capital with 0 % of utilisation rate
        irsVars.slope1 = irs.variableRateSlope1(); // rate of increase of cost of debt up to Optimal Utilisation Rate
        irsVars.slope2 = irs.variableRateSlope2(); // rate of increase of cost of debt above Optimal Utilisation Rate

        // acceptableCosts should always be > baseVariableBorrowRate
        // If it's not this will revert since the strategist set the wrong
        // acceptableCosts value
        if (
            vars.utilizationRate < irsVars.optimalRate &&
            acceptableCostsRay < irsVars.baseRate.add(irsVars.slope1)
        ) {
            // we solve Aave's Interest Rates equation for sub optimal utilisation rates
            // IR = BASERATE + SLOPE1 * CURRENT_UTIL_RATE / OPTIMAL_UTIL_RATE
            vars.targetUtilizationRate = (acceptableCostsRay.sub(irsVars.baseRate))
                .rayMul(irsVars.optimalRate)
                .rayDiv(irsVars.slope1);
        } else {
            // Special case where protocol is above utilization rate but we want
            // a lower interest rate than (base + slope1)
            if (acceptableCostsRay < irsVars.baseRate.add(irsVars.slope1)) {
                return (vars.totalDebt, 0);
            }

            // we solve Aave's Interest Rates equation for utilisation rates above optimal U 
            // IR = BASERATE + SLOPE1 + SLOPE2 * (CURRENT_UTIL_RATE - OPTIMAL_UTIL_RATE) / (1-OPTIMAL_UTIL_RATE)
            vars.targetUtilizationRate = (
                acceptableCostsRay.sub(irsVars.baseRate.add(irsVars.slope1))
            )
                .rayMul(uint256(1e27).sub(irsVars.optimalRate))
                .rayDiv(irsVars.slope2)
                .add(irsVars.optimalRate);
        }

        vars.maxProtocolDebt = vars
            .totalLiquidity
            .rayMul(vars.targetUtilizationRate)
            .rayDiv(1e27);

        return (vars.totalDebt, vars.maxProtocolDebt);
    }

    function _borrowInvestmentToken(uint256 amount) internal {
        if (amount == 0) {
            return;
        }

        _lendingPool().borrow(
            address(investmentToken),
            amount,
            2,
            referral,
            address(this)
        );
    }

    function _repayInvestmentTokenDebt(uint256 amount) internal {
        if (amount == 0) {
            return;
        }

        (, uint256 debtInETH, , , , ) = _getAaveUserAccountData();

        uint256 balance = balanceOfInvestmentToken();
        amount = Math.min(amount, balance);

        uint256 toRepayIT = Math.min(_ethToInvestmentToken(debtInETH), amount);
        _checkAllowance(
            address(_lendingPool()),
            address(investmentToken),
            toRepayIT
        );
        // TODO: check which are the units of the toRepayIT
        _lendingPool().repay(
            address(investmentToken),
            toRepayIT,
            2,
            address(this)
        );
    }

    function _depositInYVault() internal {
        if (balanceOfInvestmentToken() == 0) {
            return;
        }

        _checkAllowance(
            address(yVault),
            address(investmentToken),
            balanceOfInvestmentToken()
        );
        yVault.deposit();
    }

    function _claimRewards() internal {
        if (isIncentivised) {
            // redeem AAVE from stkAave
            uint256 stkAaveBalance =
                IERC20(address(stkAave)).balanceOf(address(this));
            if (stkAaveBalance > 0 && _checkCooldown()) {
                stkAave.redeem(address(this), stkAaveBalance);
            }

            // sell AAVE for want
            uint256 aaveBalance = IERC20(AAVE).balanceOf(address(this));
            _sellAAVEForWant(aaveBalance);

            // claim rewards
            address[] memory assets = new address[](1);
            assets[0] = address(aToken);
            assets[1] = address(variableDebtToken);
            uint256 pendingRewards =
                _incentivesController().getRewardsBalance(
                    assets,
                    address(this)
                );
            if (pendingRewards > 0) {
                _incentivesController().claimRewards(
                    assets,
                    pendingRewards,
                    address(this)
                );
            }

            // request start of cooldown period
            if (IERC20(address(stkAave)).balanceOf(address(this)) > 0) {
                stkAave.cooldown();
            }
        }
    }

    //withdraw an amount including any want balance
    function _withdrawFromAave(uint256 amount) internal returns (uint256) {
        // We first repay whatever we need to repay to keep healthy ratios
        uint256 amountToRepayIT = _calculateAmountToRepay(amount);
        uint256 withdrawnIT = _withdrawFromYVault(amountToRepayIT); // we withdraw from investmentToken vault
        _repayInvestmentTokenDebt(withdrawnIT); // we repay the investmentToken debt with Aave
        
        uint256 balanceUnderlying = balanceOfAToken();
        uint256 looseBalance = balanceOfWant();
        uint256 total = balanceUnderlying.add(looseBalance);
        if (amount > total) {
            amount = total;
        }

        if (looseBalance >= amount) {
            return amount;
        }

        uint256 maxWithdrawal =
            Math.min(_maxWithdrawal(), want.balanceOf(address(aToken)));

        uint256 toWithdraw = Math.min(amount.sub(looseBalance), maxWithdrawal);
        if (toWithdraw > 0) {
            _checkAllowance(
                address(_lendingPool()),
                address(aToken),
                toWithdraw
            );
            _lendingPool().withdraw(address(want), toWithdraw, address(this));
        }

        looseBalance = balanceOfWant();
        return looseBalance;
    }

    function _maxWithdrawal() internal view returns (uint256) {
        (uint256 totalCollateralETH, uint256 totalDebtETH, , , uint256 ltv, ) =
            _getAaveUserAccountData();
        uint256 minCollateralETH = totalDebtETH.mul(MAX_BPS).div(ltv);
        return _ethToWant(totalCollateralETH.sub(minCollateralETH));
    }

    function _calculateAmountToRepay(uint256 amount)
        internal
        view
        returns (uint256)
    {
        if (amount == 0) {
            return 0;
        }

        // we check if the collateral that we are withdrawing leaves us in a risky range, we then take action
        (
            uint256 totalCollateralETH,
            uint256 totalDebtETH,
            ,
            uint256 currentLiquidationThreshold,
            ,

        ) = _getAaveUserAccountData();

        uint256 amountToWithdrawETH = _wantToETH(amount);
        // calculate the collateral that we are leaving after withdrawing
        uint256 newCollateral =
            amountToWithdrawETH < totalCollateralETH
                ? totalCollateralETH.sub(amountToWithdrawETH)
                : 0;
        uint256 ltvAfterWithdrawal =
            newCollateral > 0
                ? totalDebtETH.mul(MAX_BPS).div(newCollateral)
                : type(uint256).max;
        // check if the new LTV is in UNHEALTHY range
        // remember that if balance > _amountNeeded, ltvAfterWithdrawal == 0 (0 risk)
        // this is not true but the effect will be the same
        uint256 warningLTV = _getWarningLTV(currentLiquidationThreshold);

        if (ltvAfterWithdrawal <= warningLTV) {
            return 0;
        }

        uint256 targetLTV = _getTargetLTV(currentLiquidationThreshold);
        // WARNING: this only works for a single collateral asset, otherwise liquidationThreshold might change depending on the collateral being withdrawn
        // e.g. we have USDC + WBTC as collateral, end liquidationThreshold will be different depending on which asset we withdraw
        uint256 newTargetDebt = targetLTV.mul(newCollateral).div(MAX_BPS);
        return _ethToInvestmentToken(totalDebtETH.sub(newTargetDebt));
    }

    function _depositToAave(uint256 amount) internal {
        if (amount == 0) {
            return;
        }

        ILendingPool lp = _lendingPool();
        _checkAllowance(address(lp), address(want), amount);
        lp.deposit(address(want), amount, address(this), referral);
    }

    function _checkCooldown() internal view returns (bool) {
        if (!isIncentivised) {
            return false;
        }

        uint256 cooldownStartTimestamp =
            IStakedAave(stkAave).stakersCooldowns(address(this));
        uint256 COOLDOWN_SECONDS = IStakedAave(stkAave).COOLDOWN_SECONDS();
        uint256 UNSTAKE_WINDOW = IStakedAave(stkAave).UNSTAKE_WINDOW();
        if (block.timestamp >= cooldownStartTimestamp.add(COOLDOWN_SECONDS)) {
            return
                block.timestamp.sub(
                    cooldownStartTimestamp.add(COOLDOWN_SECONDS)
                ) <=
                UNSTAKE_WINDOW ||
                cooldownStartTimestamp == 0;
        }

        return false;
    }

    function _checkAllowance(
        address _contract,
        address _token,
        uint256 _amount
    ) internal {
        if (IERC20(_token).allowance(address(this), _contract) < _amount) {
            IERC20(_token).safeApprove(_contract, 0);
            IERC20(_token).safeApprove(_contract, type(uint256).max);
        }
    }

    function _takeVaultProfit() internal {
        uint256 _debt = balanceOfDebt();
        uint256 _valueInVault = _valueOfInvestment();
        if (_debt >= _valueInVault) {
            return;
        }

        uint256 profit = _valueInVault.sub(_debt);
        uint256 ySharesToWithdraw = _investmentTokenToYShares(profit);
        if (ySharesToWithdraw > 0) {
            yVault.withdraw(ySharesToWithdraw);
            _sellInvestmentForWant(balanceOfInvestmentToken());
        }
    }

    // ----------------- INTERNAL CALCS -----------------
    function _borrowingRate(uint256 _additionalBorrow)
        internal
        view
        returns (uint256)
    {
        (
            uint256 availableLiquidity,
            uint256 totalStableDebt,
            uint256 totalVariableDebt,
            ,
            uint256 variableBorrowRate,
            ,
            uint256 averageStableBorrowRate,
            ,
            ,

        ) = protocolDataProvider.getReserveData(address(investmentToken));

        // If we are not adding anything, variable borrow rate is enough
        if (_additionalBorrow == 0) {
            return variableBorrowRate;
        }

        DataTypes.ReserveData memory reserveData =
            _lendingPool().getReserveData(address(investmentToken));
        uint256 newTotalVariableDebt = totalVariableDebt.add(_additionalBorrow);

        (, , , , uint256 reserveFactor, , , , , ) =
            protocolDataProvider.getReserveConfigurationData(address(want));

        (, , uint256 newVariableBorrowRate) =
            IReserveInterestRateStrategy(
                reserveData
                    .interestRateStrategyAddress
            )
                .calculateInterestRates(
                address(investmentToken),
                availableLiquidity,
                totalStableDebt,
                newTotalVariableDebt,
                averageStableBorrowRate,
                reserveFactor
            );

        return newVariableBorrowRate;
    }

    function balanceOfWant() public view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function balanceOfInvestmentToken() public view returns (uint256) {
        return investmentToken.balanceOf(address(this));
    }

    function balanceOfAToken() public view returns (uint256) {
        return aToken.balanceOf(address(this));
    }

    function balanceOfDebt() public view returns (uint256) {
        // TODO: return liabilities
        (, uint256 ethDebt, , , , ) =
            _lendingPool().getUserAccountData(address(this));
        return _ethToInvestmentToken(ethDebt);
    }

    function _balanceOfYShares() internal view returns (uint256) {
        return yVault.balanceOf(address(this));
    }

    function _getPricePerYShare() internal view returns (uint256) {
        return yVault.pricePerShare();
    }

    function _valueOfInvestment() internal view returns (uint256) {
        return
            _balanceOfYShares().mul(_getPricePerYShare()).div(
                10**yVault.decimals()
            );
    }

    function _investmentTokenToYShares(uint256 amount)
        internal
        view
        returns (uint256)
    {
        return amount.mul(10**yVault.decimals()).div(_getPricePerYShare());
    }

    function _getAaveUserAccountData()
        internal
        view
        returns (
            uint256 totalCollateralETH,
            uint256 totalDebtETH,
            uint256 availableBorrowsETH,
            uint256 currentLiquidationThreshold,
            uint256 ltv,
            uint256 healthFactor
        )
    {
        return _lendingPool().getUserAccountData(address(this));
    }

    function _getTargetLTV(uint256 liquidationThreshold)
        internal
        view
        returns (uint256)
    {
        return liquidationThreshold.mul(targetLTVMultiplier).div(MAX_BPS);
    }

    function _getWarningLTV(uint256 liquidationThreshold)
        internal
        view
        returns (uint256)
    {
        return liquidationThreshold.mul(warningLTVMultiplier).div(MAX_BPS);
    }

    // ----------------- TOKEN CONVERSIONS -----------------

    function _sellAAVEForWant(uint256 _amount) internal {
        if (_amount == 0) {
            return;
        }

        address[] memory path;

        if (address(want) == address(WETH)) {
            path = new address[](2);
            path[0] = address(AAVE);
            path[1] = address(want);
        } else {
            path = new address[](3);
            path[0] = address(AAVE);
            path[1] = address(WETH);
            path[2] = address(want);
        }

        _checkAllowance(address(router), address(AAVE), _amount);

        router.swapExactTokensForTokens(_amount, 0, path, address(this), now);
    }

    function _sellInvestmentForWant(uint256 _amount) internal {
        if (_amount == 0) {
            return;
        }

        // NOTE: 1:1
        if (address(want) == address(investmentToken)) {
            return;
        }

        address[] memory path;
        if (
            address(want) == address(WETH) ||
            address(investmentToken) == address(WETH)
        ) {
            path = new address[](2);
            path[0] = address(investmentToken);
            path[1] = address(want);
        } else {
            path = new address[](3);
            path[0] = address(investmentToken);
            path[1] = address(WETH);
            path[2] = address(want);
        }

        _checkAllowance(address(router), path[0], _amount);

        router.swapExactTokensForTokens(_amount, 0, path, address(this), now);
    }

    function _AAVEtoWant(uint256 _amount) internal view returns (uint256) {
        if (_amount == 0) {
            return 0;
        }

        address[] memory path;

        if (address(want) == address(WETH)) {
            path = new address[](2);
            path[0] = address(AAVE);
            path[1] = address(want);
        } else {
            path = new address[](3);
            path[0] = address(AAVE);
            path[1] = address(WETH);
            path[2] = address(want);
        }

        uint256[] memory amounts = router.getAmountsOut(_amount, path);
        return amounts[amounts.length - 1];
    }

    function _wantToInvestmentToken(uint256 _amount)
        internal
        view
        returns (uint256)
    {
        if (_amount == 0) {
            return 0;
        }

        // NOTE: 1:1
        if (address(want) == address(investmentToken)) {
            return _amount;
        }

        address[] memory path;
        if (
            address(want) == address(WETH) ||
            address(investmentToken) == address(WETH)
        ) {
            path = new address[](2);
            path[0] = address(want);
            path[1] = address(investmentToken);
        } else {
            path = new address[](3);
            path[0] = address(want);
            path[1] = address(WETH);
            path[2] = address(investmentToken);
        }

        uint256[] memory amounts = router.getAmountsOut(_amount, path);
        return amounts[amounts.length - 1];
    }

    function _investmentTokenToWant(uint256 _amount)
        internal
        view
        returns (uint256)
    {
        if (_amount == 0) {
            return 0;
        }

        // NOTE: 1:1
        if (address(want) == address(investmentToken)) {
            return _amount;
        }

        address[] memory path;
        if (
            address(want) == address(WETH) ||
            address(investmentToken) == address(WETH)
        ) {
            path = new address[](2);
            path[0] = address(investmentToken);
            path[1] = address(want);
        } else {
            path = new address[](3);
            path[0] = address(investmentToken);
            path[1] = address(WETH);
            path[2] = address(want);
        }

        uint256[] memory amounts = router.getAmountsOut(_amount, path);
        return amounts[amounts.length - 1];
    }

    function _investmentTokenToETH(uint256 _amount)
        internal
        view
        returns (uint256)
    {
        if (_amount == 0) {
            return 0;
        }

        // NOTE: 1:1
        if (address(investmentToken) == address(WETH)) {
            return _amount;
        }

        address[] memory path = new address[](2);
        path[0] = address(investmentToken);
        path[1] = address(WETH);

        uint256[] memory amounts = router.getAmountsOut(_amount, path);
        return amounts[amounts.length - 1];
    }

    function _wantToETH(uint256 _amount) internal view returns (uint256) {
        if (_amount == 0) {
            return 0;
        }

        // NOTE: 1:1
        if (address(want) == address(WETH)) {
            return _amount;
        }

        address[] memory path = new address[](2);
        path[0] = address(want);
        path[1] = address(WETH);

        uint256[] memory amounts = router.getAmountsOut(_amount, path);
        return amounts[amounts.length - 1];
    }

    function _ethToWant(uint256 _amount) internal view returns (uint256) {
        if (_amount == 0) {
            return 0;
        }

        // NOTE: 1:1
        if (address(want) == address(WETH)) {
            return _amount;
        }

        address[] memory path = new address[](2);
        path[0] = address(WETH);
        path[1] = address(want);

        uint256[] memory amounts = router.getAmountsOut(_amount, path);
        return amounts[amounts.length - 1];
    }

    function _ethToInvestmentToken(uint256 _amount)
        internal
        view
        returns (uint256)
    {
        if (_amount == 0) {
            return 0;
        }

        // NOTE: 1:1
        if (address(investmentToken) == address(WETH)) {
            return _amount;
        }

        address[] memory path = new address[](2);
        path[0] = address(WETH);
        path[1] = address(investmentToken);

        uint256[] memory amounts = router.getAmountsOut(_amount, path);
        return amounts[amounts.length - 1];
    }

    // ----------------- INTERNAL SUPPORT GETTERS -----------------

    function _getLiquidationLTV() internal view returns (uint256) {}

    function _lendingPool() internal view returns (ILendingPool lendingPool) {
        lendingPool = ILendingPool(
            protocolDataProvider.ADDRESSES_PROVIDER().getLendingPool()
        );
    }

    function _incentivesController()
        internal
        view
        returns (IAaveIncentivesController)
    {
        if (isIncentivised) {
            return aToken.getIncentivesController();
        } else {
            return IAaveIncentivesController(0);
        }
    }

    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {}
}
