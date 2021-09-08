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
import "./libraries/AaveLenderBorrowerLib.sol";

import "./interfaces/ISwap.sol";
import "./interfaces/IVault.sol";
import "./interfaces/aave/IAToken.sol";
import "./interfaces/IOptionalERC20.sol";
import "./interfaces/aave/IStakedAave.sol";
import "./interfaces/aave/IPriceOracle.sol";
import "./interfaces/aave/ILendingPool.sol";
import "./interfaces/aave/IVariableDebtToken.sol";
import "./interfaces/aave/IProtocolDataProvider.sol";
import "./interfaces/aave/IAaveIncentivesController.sol";
import "./interfaces/aave/IReserveInterestRateStrategy.sol";

contract Strategy is BaseStrategy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeMath for uint256;
    using WadRayMath for uint256;

    // max interest rate we can afford to pay for borrowing investment token
    // amount in Ray (1e27 = 100%)
    uint256 public acceptableCostsRay = WadRayMath.RAY;

    // max amount to borrow. used to manually limit amount (for yVault to keep APY)
    uint256 public maxTotalBorrowIT;

    bool public isWantIncentivised;
    bool public isInvestmentTokenIncentivised;

    // if set to true, the strategy will not try to repay debt by selling want
    bool public leaveDebtBehind;

    // Aave's referral code
    uint16 internal referral;

    // NOTE: LTV = Loan-To-Value = debt/collateral

    // Target LTV: ratio up to which which we will borrow
    uint16 public targetLTVMultiplier = 6_000;

    // Warning LTV: ratio at which we will repay
    uint16 public warningLTVMultiplier = 8_000; // 80% of liquidation LTV

    // support
    uint16 internal constant MAX_BPS = 10_000; // 100%
    uint16 internal constant MAX_MULTIPLIER = 9_000; // 90%

    IAToken internal aToken;
    IVariableDebtToken internal variableDebtToken;
    IVault public yVault;
    IERC20 internal investmentToken;

    ISwap public router;

    IStakedAave internal constant stkAave =
        IStakedAave(0x4da27a545c0c5B758a6BA100e3a049001de870f5);

    address internal constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address internal constant AAVE = 0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9;

    uint256 internal minThreshold;
    uint256 public maxLoss;
    string internal strategyName;

    event RepayDebt(uint256 repayAmount, uint256 previousDebtBalance);

    constructor(
        address _vault,
        address _yVault,
        string memory _strategyName
    ) public BaseStrategy(_vault) {
        _initializeThis(_yVault, _strategyName);
    }

    // ----------------- PUBLIC VIEW FUNCTIONS -----------------

    function name() external view override returns (string memory) {
        return strategyName;
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        // not taking into account aave rewards (they are staked and not accesible)
        return
            balanceOfWant() // balance of want
                .add(balanceOfAToken()) // asset suplied as collateral
                .add(
                _fromETH(
                    _toETH(_valueOfInvestment(), address(investmentToken)),
                    address(want)
                )
            ) // current value of assets deposited in vault
                .sub(
                _fromETH(
                    _toETH(balanceOfDebt(), address(investmentToken)),
                    address(want)
                )
            ); // liabilities
    }

    // ----------------- SETTERS -----------------
    // we put all together to save contract bytecode (!)
    function setStrategyParams(
        uint16 _targetLTVMultiplier,
        uint16 _warningLTVMultiplier,
        uint256 _acceptableCostsRay,
        uint16 _aaveReferral,
        uint256 _maxTotalBorrowIT,
        bool _isWantIncentivised,
        bool _isInvestmentTokenIncentivised,
        bool _leaveDebtBehind,
        uint256 _maxLoss
    ) external onlyEmergencyAuthorized {
        require(
            _warningLTVMultiplier <= MAX_MULTIPLIER &&
                _targetLTVMultiplier <= _warningLTVMultiplier
        );
        targetLTVMultiplier = _targetLTVMultiplier;
        warningLTVMultiplier = _warningLTVMultiplier;
        acceptableCostsRay = _acceptableCostsRay;
        maxTotalBorrowIT = _maxTotalBorrowIT;
        referral = _aaveReferral;
        isWantIncentivised = _isWantIncentivised;
        isInvestmentTokenIncentivised = _isInvestmentTokenIncentivised;
        leaveDebtBehind = _leaveDebtBehind;

        require(_maxLoss <= 10_000);
        maxLoss = _maxLoss;
    }

    // Where to route token swaps
    // Access control is stricter in this method as it will be sent funds
    function setSwapRouter(ISwap _router) external onlyGovernance {
        router = _router;
    }

    function _initializeThis(address _yVault, string memory _strategyName)
        internal
    {
        // Make sure we only initialize one time
        require(address(yVault) == address(0)); // dev: strategy already initialized

        yVault = IVault(_yVault);
        investmentToken = IERC20(IVault(_yVault).token());
        (address _aToken, , ) =
            _protocolDataProvider().getReserveTokensAddresses(address(want));
        aToken = IAToken(_aToken);
        (, , address _variableDebtToken) =
            _protocolDataProvider().getReserveTokensAddresses(
                address(investmentToken)
            );

        variableDebtToken = IVariableDebtToken(_variableDebtToken);
        minThreshold = (10**(yVault.decimals())).div(100); // 0.01 minThreshold

        // Set default router to SushiSwap
        router = ISwap(0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F);

        strategyName = _strategyName;
    }

    function initialize(
        address _vault,
        address _yVault,
        string memory _strategyName
    ) public {
        // Make sure we only initialize one time
        require(address(yVault) == address(0)); // dev: strategy already initialized

        address sender = msg.sender;
        _initialize(_vault, sender, sender, sender);
        _initializeThis(_yVault, _strategyName);
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
        uint256 totalDebt = vault.strategies(address(this)).totalDebt;

        // claim rewards from Aave's Liquidity Mining Program
        _claimRewards();

        // claim rewards from yVault
        _takeVaultProfit();

        uint256 totalAssetsAfterProfit = estimatedTotalAssets();

        _profit = totalAssetsAfterProfit > totalDebt
            ? totalAssetsAfterProfit.sub(totalDebt)
            : 0;

        uint256 _amountFreed;
        (_amountFreed, _loss) = liquidatePosition(
            _debtOutstanding.add(_profit)
        );
        _debtPayment = Math.min(_debtOutstanding, _amountFreed);

        if (_loss > _profit) {
            // Example:
            // debtOutstanding 100, profit 50, _amountFreed 100, _loss 50
            // loss should be 0, (50-50)
            // profit should endup in 0
            _loss = _loss.sub(_profit);
            _profit = 0;
        } else {
            // Example:
            // debtOutstanding 100, profit 50, _amountFreed 140, _loss 10
            // _profit should be 40, (50 profit - 10 loss)
            // loss should end up in be 0
            _profit = _profit.sub(_loss);
            _loss = 0;
        }
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        uint256 wantBalance = balanceOfWant();

        // if we have enough want to deposit more into Aave, we do
        // NOTE: we do not skip the rest of the function if we don't as it may need to repay or take on more debt
        if (wantBalance > _debtOutstanding) {
            uint256 amountToDeposit = wantBalance.sub(_debtOutstanding);
            _depositToAave(amountToDeposit);
        }

        // NOTE: debt + collateral calcs are done in ETH
        (
            uint256 totalCollateralETH,
            uint256 totalDebtETH,
            uint256 availableBorrowsETH,
            uint256 currentLiquidationThreshold,
            ,

        ) = _getAaveUserAccountData();

        // if there is no want deposited into aave, don't do nothing
        // this means no debt is borrowed from aave too
        if (totalCollateralETH == 0) {
            return;
        }

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
        (
            uint256 currentProtocolDebt,
            uint256 maxProtocolDebt,
            uint256 targetUtilisationRay
        ) =
            AaveLenderBorrowerLib.calcMaxDebt(
                address(investmentToken),
                acceptableCostsRay
            );

        if (targetLTV > currentLTV && currentProtocolDebt < maxProtocolDebt) {
            // SUBOPTIMAL RATIO: our current Loan-to-Value is lower than what we want
            // AND costs are lower than our max acceptable costs

            // we need to take on more debt
            uint256 targetDebtETH =
                totalCollateralETH.mul(targetLTV).div(MAX_BPS);

            uint256 amountToBorrowETH = targetDebtETH.sub(totalDebtETH); // safe bc we checked ratios
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

            uint256 maxTotalBorrowETH =
                _toETH(maxTotalBorrowIT, address(investmentToken));
            if (totalDebtETH.add(amountToBorrowETH) > maxTotalBorrowETH) {
                amountToBorrowETH = maxTotalBorrowETH > totalDebtETH
                    ? maxTotalBorrowETH.sub(totalDebtETH)
                    : 0;
            }

            // convert to InvestmentToken
            uint256 amountToBorrowIT =
                _fromETH(amountToBorrowETH, address(investmentToken));

            if (amountToBorrowIT > 0) {
                _lendingPool().borrow(
                    address(investmentToken),
                    amountToBorrowIT,
                    2,
                    referral,
                    address(this)
                );
            }
        } else if (
            currentLTV > warningLTV || currentProtocolDebt > maxProtocolDebt
        ) {
            // UNHEALTHY RATIO
            // we may be in this case if the current cost of capital is higher than our max cost of capital
            // we repay debt to set it to targetLTV
            uint256 targetDebtETH =
                targetLTV.mul(totalCollateralETH).div(MAX_BPS);
            uint256 amountToRepayETH =
                targetDebtETH < totalDebtETH
                    ? totalDebtETH.sub(targetDebtETH)
                    : 0;

            if (maxProtocolDebt == 0) {
                amountToRepayETH = totalDebtETH;
            } else if (currentProtocolDebt > maxProtocolDebt) {
                // NOTE: take into account that we are withdrawing from yvVault which might have a GenLender lending to Aave
                // REPAY = (currentProtocolDebt - maxProtocolDebt) / (1 - TargetUtilisation)
                // coming from
                // TargetUtilisation = (totalDebt - REPAY) / (currentLiquidity - REPAY)
                // currentLiquidity = maxProtocolDebt / TargetUtilisation

                uint256 iterativeRepayAmountETH =
                    currentProtocolDebt
                        .sub(maxProtocolDebt)
                        .mul(WadRayMath.RAY)
                        .div(uint256(WadRayMath.RAY).sub(targetUtilisationRay));
                amountToRepayETH = Math.max(
                    amountToRepayETH,
                    iterativeRepayAmountETH
                );
            }
            emit RepayDebt(amountToRepayETH, totalDebtETH);

            uint256 amountToRepayIT =
                _fromETH(amountToRepayETH, address(investmentToken));
            uint256 withdrawnIT = _withdrawFromYVault(amountToRepayIT); // we withdraw from investmentToken vault
            _repayInvestmentTokenDebt(withdrawnIT); // we repay the investmentToken debt with Aave
        }

        uint256 balanceIT = balanceOfInvestmentToken();
        if (balanceIT > 0) {
            _checkAllowance(
                address(yVault),
                address(investmentToken),
                balanceIT
            );

            yVault.deposit();
        }
    }

    function liquidateAllPositions()
        internal
        override
        returns (uint256 _amountFreed)
    {
        (_amountFreed, ) = liquidatePosition(estimatedTotalAssets());
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
        // NOTE: repayment amount is in investmentToken
        // NOTE: collateral and debt calcs are done in ETH (always, see Aave docs)

        // We first repay whatever we need to repay to keep healthy ratios
        uint256 amountToRepayIT = _calculateAmountToRepay(_amountNeeded);
        uint256 withdrawnIT = _withdrawFromYVault(amountToRepayIT); // we withdraw from investmentToken vault
        _repayInvestmentTokenDebt(withdrawnIT); // we repay the investmentToken debt with Aave

        // it will return the free amount of want
        _withdrawWantFromAave(_amountNeeded);

        balance = balanceOfWant();
        // we check if we withdrew less than expected AND should buy investmentToken with want (realising losses)
        if (
            _amountNeeded > balance &&
            balanceOfDebt() > 0 && // still some debt remaining
            balanceOfInvestmentToken().add(_valueOfInvestment()) == 0 && // but no capital to repay
            !leaveDebtBehind // if set to true, the strategy will not try to repay debt by selling want
        ) {
            // using this part of code will result in losses but it is necessary to unlock full collateral in case of wind down
            // we calculate how much want we need to fulfill the want request
            uint256 remainingAmountWant = _amountNeeded.sub(balance);
            // then calculate how much InvestmentToken we need to unlock collateral
            amountToRepayIT = _calculateAmountToRepay(remainingAmountWant);

            // we buy investmentToken with Want
            _buyInvestmentTokenWithWant(amountToRepayIT);

            // we repay debt to actually unlock collateral
            // after this, balanceOfDebt should be 0
            _repayInvestmentTokenDebt(amountToRepayIT);

            // then we try withdraw once more
            _withdrawWantFromAave(remainingAmountWant);
        }

        uint256 totalAssets = balanceOfWant();
        if (_amountNeeded > totalAssets) {
            _liquidatedAmount = totalAssets;
            _loss = _amountNeeded.sub(totalAssets);
        } else {
            _liquidatedAmount = _amountNeeded;
        }
    }

    function delegatedAssets() external view override returns (uint256) {
        // returns total debt borrowed in want (which is the delegatedAssets)
        return
            _fromETH(
                _toETH(balanceOfDebt(), address(investmentToken)),
                address(want)
            );
    }

    function prepareMigration(address _newStrategy) internal override {
        // nothing to do since debt cannot be migrated
    }

    function harvestTrigger(uint256 callCost)
        public
        view
        override
        returns (bool)
    {
        // we harvest if:
        // 1. stakedAave is ready to be converted to Aave and sold

        return
            _checkCooldown() ||
            super.harvestTrigger(_fromETH(callCost, address(want)));
    }

    function tendTrigger(uint256 callCost) public view override returns (bool) {
        // we adjust position if:
        // 1. LTV ratios are not in the HEALTHY range (either we take on more debt or repay debt)
        // 2. costs are not acceptable and we need to repay debt
        (
            uint256 totalCollateralETH,
            uint256 totalDebtETH,
            ,
            uint256 currentLiquidationThreshold,
            ,

        ) = _getAaveUserAccountData();

        uint256 targetLTV = _getTargetLTV(currentLiquidationThreshold);
        uint256 warningLTV = _getWarningLTV(currentLiquidationThreshold);

        return
            AaveLenderBorrowerLib.shouldRebalance(
                address(investmentToken),
                acceptableCostsRay,
                targetLTV,
                warningLTV,
                totalCollateralETH,
                totalDebtETH
            );
    }

    // ----------------- INTERNAL FUNCTIONS SUPPORT -----------------

    function _withdrawFromYVault(uint256 _amountIT) internal returns (uint256) {
        if (_amountIT == 0) {
            return 0;
        }
        // no need to check allowance bc the contract == token
        uint256 balancePrior = balanceOfInvestmentToken();
        uint256 sharesToWithdraw =
            Math.min(
                _investmentTokenToYShares(_amountIT),
                yVault.balanceOf(address(this))
            );
        if (sharesToWithdraw == 0) {
            return 0;
        }
        yVault.withdraw(sharesToWithdraw, address(this), maxLoss);
        return balanceOfInvestmentToken().sub(balancePrior);
    }

    function _repayInvestmentTokenDebt(uint256 amount) internal {
        if (amount == 0) {
            return;
        }

        // we cannot pay more than loose balance
        amount = Math.min(amount, balanceOfInvestmentToken());
        // we cannot pay more than we owe
        amount = Math.min(amount, balanceOfDebt());

        _checkAllowance(
            address(_lendingPool()),
            address(investmentToken),
            amount
        );

        if (amount > 0) {
            _lendingPool().repay(
                address(investmentToken),
                amount,
                uint256(2),
                address(this)
            );
        }
    }

    function _claimRewards() internal {
        if (isInvestmentTokenIncentivised || isWantIncentivised) {
            // redeem AAVE from stkAave
            uint256 stkAaveBalance =
                IERC20(address(stkAave)).balanceOf(address(this));

            if (stkAaveBalance > 0 && _checkCooldown()) {
                // claim AAVE rewards
                stkAave.claimRewards(address(this), type(uint256).max);
                stkAave.redeem(address(this), stkAaveBalance);
            }

            // sell AAVE for want
            // a minimum balance of 0.01 AAVE is required
            uint256 aaveBalance = IERC20(AAVE).balanceOf(address(this));
            if (aaveBalance > 1e15) {
                _sellAForB(aaveBalance, address(AAVE), address(want));
            }

            // claim rewards
            // only add to assets those assets that are incentivised
            address[] memory assets;
            if (isInvestmentTokenIncentivised && isWantIncentivised) {
                assets = new address[](2);
                assets[0] = address(aToken);
                assets[1] = address(variableDebtToken);
            } else if (isInvestmentTokenIncentivised) {
                assets = new address[](1);
                assets[0] = address(variableDebtToken);
            } else if (isWantIncentivised) {
                assets = new address[](1);
                assets[0] = address(aToken);
            }

            _incentivesController().claimRewards(
                assets,
                type(uint256).max,
                address(this)
            );

            // request start of cooldown period
            uint256 cooldownStartTimestamp =
                IStakedAave(stkAave).stakersCooldowns(address(this));
            uint256 COOLDOWN_SECONDS = IStakedAave(stkAave).COOLDOWN_SECONDS();
            uint256 UNSTAKE_WINDOW = IStakedAave(stkAave).UNSTAKE_WINDOW();
            if (
                IERC20(address(stkAave)).balanceOf(address(this)) > 0 &&
                (cooldownStartTimestamp == 0 ||
                    block.timestamp >
                    cooldownStartTimestamp.add(COOLDOWN_SECONDS).add(
                        UNSTAKE_WINDOW
                    ))
            ) {
                stkAave.cooldown();
            }
        }
    }

    //withdraw an amount including any want balance
    function _withdrawWantFromAave(uint256 amount) internal {
        uint256 balanceUnderlying = balanceOfAToken();
        if (amount > balanceUnderlying) {
            amount = balanceUnderlying;
        }

        uint256 maxWithdrawal =
            Math.min(_maxWithdrawal(), want.balanceOf(address(aToken)));

        uint256 toWithdraw = Math.min(amount, maxWithdrawal);
        if (toWithdraw > 0) {
            _checkAllowance(
                address(_lendingPool()),
                address(aToken),
                toWithdraw
            );
            _lendingPool().withdraw(address(want), toWithdraw, address(this));
        }
    }

    function _maxWithdrawal() internal view returns (uint256) {
        (uint256 totalCollateralETH, uint256 totalDebtETH, , , uint256 ltv, ) =
            _getAaveUserAccountData();
        uint256 minCollateralETH =
            ltv > 0 ? totalDebtETH.mul(MAX_BPS).div(ltv) : totalCollateralETH;
        if (minCollateralETH > totalCollateralETH) {
            return 0;
        }
        return
            _fromETH(totalCollateralETH.sub(minCollateralETH), address(want));
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
        uint256 warningLTV = _getWarningLTV(currentLiquidationThreshold);
        uint256 targetLTV = _getTargetLTV(currentLiquidationThreshold);
        uint256 amountETH = _toETH(amount, address(want));
        return
            AaveLenderBorrowerLib.calculateAmountToRepay(
                amountETH,
                totalCollateralETH,
                totalDebtETH,
                warningLTV,
                targetLTV,
                address(investmentToken),
                minThreshold
            );
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
        return
            AaveLenderBorrowerLib.checkCooldown(
                isWantIncentivised,
                isInvestmentTokenIncentivised,
                address(stkAave)
            );
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
            yVault.withdraw(ySharesToWithdraw, address(this), maxLoss);
            _sellAForB(
                balanceOfInvestmentToken(),
                address(investmentToken),
                address(want)
            );
        }
    }

    // ----------------- INTERNAL CALCS -----------------
    function balanceOfWant() internal view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function balanceOfInvestmentToken() internal view returns (uint256) {
        return investmentToken.balanceOf(address(this));
    }

    function balanceOfAToken() internal view returns (uint256) {
        return aToken.balanceOf(address(this));
    }

    function balanceOfDebt() internal view returns (uint256) {
        return variableDebtToken.balanceOf(address(this));
    }

    function _valueOfInvestment() internal view returns (uint256) {
        return
            yVault.balanceOf(address(this)).mul(yVault.pricePerShare()).div(
                10**yVault.decimals()
            );
    }

    function _investmentTokenToYShares(uint256 amount)
        internal
        view
        returns (uint256)
    {
        return amount.mul(10**yVault.decimals()).div(yVault.pricePerShare());
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
        return
            liquidationThreshold.mul(uint256(targetLTVMultiplier)).div(MAX_BPS);
    }

    function _getWarningLTV(uint256 liquidationThreshold)
        internal
        view
        returns (uint256)
    {
        return
            liquidationThreshold.mul(uint256(warningLTVMultiplier)).div(
                MAX_BPS
            );
    }

    // ----------------- TOKEN CONVERSIONS -----------------
    function getTokenOutPath(address _token_in, address _token_out)
        internal
        pure
        returns (address[] memory _path)
    {
        bool is_weth =
            _token_in == address(WETH) || _token_out == address(WETH);
        _path = new address[](is_weth ? 2 : 3);
        _path[0] = _token_in;

        if (is_weth) {
            _path[1] = _token_out;
        } else {
            _path[1] = address(WETH);
            _path[2] = _token_out;
        }
    }

    function _sellAForB(
        uint256 _amount,
        address tokenA,
        address tokenB
    ) internal {
        if (_amount == 0 || tokenA == tokenB) {
            return;
        }

        _checkAllowance(address(router), tokenA, _amount);
        router.swapExactTokensForTokens(
            _amount,
            0,
            getTokenOutPath(tokenA, tokenB),
            address(this),
            now
        );
    }

    function _buyInvestmentTokenWithWant(uint256 _amount) internal {
        if (_amount == 0 || address(investmentToken) == address(want)) {
            return;
        }

        _checkAllowance(address(router), address(want), _amount);
        router.swapTokensForExactTokens(
            _amount,
            type(uint256).max,
            getTokenOutPath(address(want), address(investmentToken)),
            address(this),
            now
        );
    }

    function _toETH(uint256 _amount, address asset)
        internal
        view
        returns (uint256)
    {
        if (
            _amount == 0 ||
            _amount == type(uint256).max ||
            address(asset) == address(WETH) // 1:1 change
        ) {
            return _amount;
        }
        return AaveLenderBorrowerLib.toETH(_amount, asset);
    }

    function ethToWant(uint256 _amtInWei)
        public
        view
        override
        returns (uint256)
    {
        return _fromETH(_amtInWei, address(want));
    }

    function _fromETH(uint256 _amount, address asset)
        internal
        view
        returns (uint256)
    {
        if (
            _amount == 0 ||
            _amount == type(uint256).max ||
            address(asset) == address(WETH) // 1:1 change
        ) {
            return _amount;
        }
        return AaveLenderBorrowerLib.fromETH(_amount, asset);
    }

    // ----------------- INTERNAL SUPPORT GETTERS -----------------

    function _lendingPool() internal view returns (ILendingPool lendingPool) {
        return AaveLenderBorrowerLib.lendingPool();
    }

    function _protocolDataProvider()
        internal
        view
        returns (IProtocolDataProvider protocolDataProvider)
    {
        return AaveLenderBorrowerLib.protocolDataProvider;
    }

    function _priceOracle() internal view returns (IPriceOracle) {
        return AaveLenderBorrowerLib.priceOracle();
    }

    function _incentivesController()
        internal
        view
        returns (IAaveIncentivesController)
    {
        return
            AaveLenderBorrowerLib.incentivesController(
                aToken,
                variableDebtToken,
                isWantIncentivised,
                isInvestmentTokenIncentivised
            );
    }

    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {}
}
