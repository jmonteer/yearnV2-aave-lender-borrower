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

import "./interfaces/ISwap.sol";
import "./interfaces/IVault.sol";
import "./interfaces/aave/IAToken.sol";
import "./libraries/SupportStructs.sol";
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
    // true if this token is incentivised
    bool public isWantIncentivised;
    bool public isInvestmentTokenIncentivised;

    // Aave's referral code
    uint16 internal referral;

    // NOTE: LTV = Loan-To-Value = debt/collateral
    // Target LTV: ratio up to which which we will borrow
    uint16 internal targetLTVMultiplier = 6_000; // 60% of liquidation LTV
    // Warning LTV: ratio at which we will repay
    uint16 internal warningLTVMultiplier = 8_000; // 80% of liquidation LTV

    // support
    uint16 internal constant MAX_BPS = 10_000; // 100%

    IAToken public aToken;
    IVariableDebtToken public variableDebtToken;
    IVault public yVault;
    IERC20 internal investmentToken;

    ISwap internal router = ISwap(0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D);

    IStakedAave internal stkAave =
        IStakedAave(0x4da27a545c0c5B758a6BA100e3a049001de870f5);

    IProtocolDataProvider internal protocolDataProvider =
        IProtocolDataProvider(0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d);

    address internal WETH = address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    address internal AAVE = address(0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9);

    // max interest rate we can afford to pay for borrowing investment token
    // amount in Ray (1e27 = 100%)
    uint256 public acceptableCostsRay = 1e27;

    // max amount to borrow. used to manually limit amount (for yVault to keep APY)
    uint256 public maxTotalBorrowIT;

    constructor(
        address _vault,
        address _yVault,
        bool _isWantIncentivised,
        bool _isInvestmentTokenIncentivised
    ) public BaseStrategy(_vault) {
        minReportDelay = 24 * 3600;
        maxReportDelay = 10 * 24 * 3600;
        profitFactor = 100;
        debtThreshold = 0;

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

        _setIsWantIncentivised(_isWantIncentivised);
        _setIsInvestmentTokenIncentivised(_isInvestmentTokenIncentivised);

        referral = 179; // currently not working but in case it is done retroactively (jmonteer's referral code)
        maxTotalBorrowIT = type(uint256).max; // set to max to avoid limits. this may trigger revert in some parts if not correctly handled
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
    // for the management to activate / deactivate incentives functionality
    function setIncentivisedTokens(
        bool _isWantIncentivised,
        bool _isInvestmentTokenIncentivised
    ) external onlyAuthorized {
        _setIsInvestmentTokenIncentivised(_isInvestmentTokenIncentivised);
        _setIsWantIncentivised(_isWantIncentivised);
    }

    function setMaxTotalBorrowIT(uint256 _maxTotalBorrowIT)
        external
        onlyAuthorized
    {
        maxTotalBorrowIT = _maxTotalBorrowIT;
    }

    function setReferralCode(uint16 _referral) external onlyAuthorized {
        referral = _referral;
    }

    function setLTVMultipliers(
        uint16 _targetLTVMultiplier,
        uint16 _warningLTVMultiplier
    ) external onlyAuthorized {
        require(
            _targetLTVMultiplier < MAX_BPS &&
                _warningLTVMultiplier < MAX_BPS &&
                _warningLTVMultiplier > _targetLTVMultiplier
        );
        targetLTVMultiplier = _targetLTVMultiplier;
        warningLTVMultiplier = _warningLTVMultiplier;
    }

    function setYVault(IVault _yVault) external onlyAuthorized {
        if (balanceOfDebt() != 0) {
            _withdrawFromYVault(_valueOfInvestment()); // we withdraw the full amount from investmentToken vault
            _repayInvestmentTokenDebt(balanceOfInvestmentToken()); // we use all of our balance to repay debt with Aave

            // we sell profits
            if (balanceOfInvestmentToken() > 0) {
                _sellInvestmentForWant(balanceOfInvestmentToken());
            }
        }

        // we are going to stop using these tokens so we need to be sure we have all 0 balance
        require(
            balanceOfInvestmentToken() == 0 &&
                balanceOfDebt() == 0 &&
                yVault.balanceOf(address(this)) == 0
        );

        // set new investment Token
        investmentToken = IERC20(IVault(_yVault).token());

        // retrieve variableDebtToken
        (, , address _variableDebtToken) =
            protocolDataProvider.getReserveTokensAddresses(
                address(investmentToken)
            );

        // set variableDebtToken
        variableDebtToken = IVariableDebtToken(_variableDebtToken);

        // change Investment Vault
        yVault = _yVault;
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

        // // claim interest from lending
        // _takeLendingProfit();
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

            _depositInYVault();
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
                amountToRepayETH = Math.max(
                    amountToRepayETH,
                    currentProtocolDebt.sub(maxProtocolDebt)
                );
            }

            uint256 amountToRepayIT =
                _fromETH(amountToRepayETH, address(investmentToken));
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

        uint256 amountToWithdrawWant = _amountNeeded.sub(balance);
        // emit Repay(0, 0, amountToWithdrawWant);
        // it will return the free amount of want
        uint256 withdrawnWant = _withdrawWantFromAave(amountToWithdrawWant);
        // we check if we withdrew less than expected AND should buy investmentToken with want (realising losses)
        if (
            amountToWithdrawWant > withdrawnWant &&
            balanceOfDebt() > 0 &&
            balanceOfInvestmentToken().add(_valueOfInvestment()) == 0
        ) {
            // using this part of code will result in losses but it is necessary to unlock full collateral in case of wind down
            // we calculate how much want we need to fulfill the want request
            uint256 remainingAmountWant =
                amountToWithdrawWant.sub(withdrawnWant);
            // then calculate how much InvestmentToken we need to unlock collateral
            uint256 amountToRepayIT =
                _calculateAmountToRepay(remainingAmountWant);
            // we buy investmentToken with Want
            _buyInvestmentTokenWithWant(amountToRepayIT);
            // we repay debt to actually unlock collateral
            // after this, balanceOfDebt should be 0
            _repayInvestmentTokenDebt(amountToRepayIT);

            // then we try withdraw once more
            _withdrawWantFromAave(remainingAmountWant);
        }

        uint256 totalAssets = balanceOfWant();
        // emit Withdrawing(amountToWithdrawWant, withdrawnWant, totalAssets);

        if (_amountNeeded > totalAssets) {
            _liquidatedAmount = totalAssets;
            _loss = _amountNeeded.sub(totalAssets);
        } else {
            _liquidatedAmount = _amountNeeded;
        }
    }

    event Withdrawing(
        uint256 amountToWithdrawWant,
        uint256 withdrawnWant,
        uint256 assets
    );

    function prepareMigration(address _newStrategy) internal override {
        // in yearn-vaults, the oldStrategy's totalDebt is set to 0 before calling migrate on BaseStrategy
        // so we need to use totalDebt of the _newStrategy even if that logic "does not make sense"
        liquidatePosition(vault.strategies(_newStrategy).totalDebt);
    }

    function harvestTrigger(uint256 callCost)
        public
        view
        override
        returns (bool)
    {
        // we harvest if:
        // 1. stakedAave is ready to be converted to Aave and sold

        return _checkCooldown() || super.harvestTrigger(callCost);
    }

    function tendTrigger(uint256 callCost) public view override returns (bool) {
        // we adjust position if:
        // 1. LTV ratios are not in the HEALTHY range (either we take on more debt or repay debt)
        // 2. costs are not acceptable and we need to repay debt

        (
            uint256 totalCollateralETH,
            uint256 totalDebtETH,
            uint256 availableBorrowsETH,
            uint256 currentLiquidationThreshold,
            uint256 ltv,
            uint256 healthFactor
        ) = _getAaveUserAccountData();

        uint256 currentLTV = totalDebtETH.mul(MAX_BPS).div(totalCollateralETH);
        uint256 targetLTV = _getTargetLTV(currentLiquidationThreshold);
        uint256 warningLTV = _getWarningLTV(currentLiquidationThreshold);
        (uint256 currentProtocolDebt, uint256 maxProtocolDebt) =
            _calculateMaxDebt();

        if (
            currentLTV < targetLTV &&
            currentProtocolDebt < maxProtocolDebt &&
            targetLTV.sub(currentLTV) > 100
        ) {
            // WE NEED TO TAKE ON MORE DEBT
            // threshold of 100 bps of difference
            return true;
        } else if (
            currentLTV > warningLTV || currentProtocolDebt > maxProtocolDebt
        ) {
            // WE NEED TO REPAY DEBT BECAUSE OF UNHEALTHY RATIO OR BORROWING COSTS
            // no threshold, take immediate action
            return true;
        }

        return super.harvestTrigger(callCost);
    }

    // ----------------- EXTERNAL FUNCTIONS MANAGEMENT -----------------

    function startCooldown() external onlyAuthorized {
        // for emergency cases
        IStakedAave(stkAave).cooldown(); // it will revert if balance of stkAave == 0
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
        yVault.withdraw(sharesToWithdraw);
        return balanceOfInvestmentToken().sub(balancePrior);
    }

    function _repayInvestmentTokenDebt(uint256 amount) internal {
        if (amount == 0) {
            return;
        }

        (, uint256 debtInETH, , , , ) = _getAaveUserAccountData();

        uint256 balance = balanceOfInvestmentToken();
        amount = Math.min(amount, balance);
        uint256 toRepayIT =
            Math.min(_fromETH(debtInETH, address(investmentToken)), amount);

        // emit Repay(balance, toRepayIT, debtInETH);
        _checkAllowance(
            address(_lendingPool()),
            address(investmentToken),
            toRepayIT
        );

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
        if (isInvestmentTokenIncentivised || isWantIncentivised) {
            // redeem AAVE from stkAave
            uint256 stkAaveBalance =
                IERC20(address(stkAave)).balanceOf(address(this));
            if (stkAaveBalance > 0 && _checkCooldown()) {
                stkAave.redeem(address(this), stkAaveBalance);
            }

            // TODO: claim staking rewards

            // sell AAVE for want
            uint256 aaveBalance = IERC20(AAVE).balanceOf(address(this));
            _sellAAVEForWant(aaveBalance);

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

    function _takeLendingProfit() internal {
        uint256 depositedWant = vault.strategies(address(this)).totalDebt;
        uint256 currentWantInAave = balanceOfAToken();

        if (depositedWant < currentWantInAave) {
            uint256 toWithdraw =
                Math.min(
                    currentWantInAave.sub(depositedWant),
                    _maxWithdrawal()
                );
            _withdrawWantFromAave(1);
        }
    }

    //withdraw an amount including any want balance
    function _withdrawWantFromAave(uint256 amount) internal returns (uint256) {
        uint256 balanceOfWantInit = balanceOfWant();
        // We first repay whatever we need to repay to keep healthy ratios
        uint256 amountToRepayIT = _calculateAmountToRepay(amount);
        uint256 withdrawnIT = _withdrawFromYVault(amountToRepayIT); // we withdraw from investmentToken vault
        _repayInvestmentTokenDebt(withdrawnIT); // we repay the investmentToken debt with Aave

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

        uint256 balanceOfWantEnd = balanceOfWant();
        return
            balanceOfWantEnd > balanceOfWantInit
                ? balanceOfWantEnd.sub(balanceOfWantInit)
                : 0;
    }

    function _maxWithdrawal() internal view returns (uint256) {
        (uint256 totalCollateralETH, uint256 totalDebtETH, , , uint256 ltv, ) =
            _getAaveUserAccountData();
        uint256 minCollateralETH = totalDebtETH.mul(MAX_BPS).div(ltv);
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

        uint256 amountToWithdrawETH = _toETH(amount, address(want));
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
            // no need of repaying debt because the LTV is ok
            return 0;
        } else if (ltvAfterWithdrawal == type(uint256).max) {
            // we are withdrawing 100% of collateral
            return _fromETH(totalDebtETH, address(investmentToken));
        }

        uint256 targetLTV = _getTargetLTV(currentLiquidationThreshold);
        // WARNING: this only works for a single collateral asset, otherwise liquidationThreshold might change depending on the collateral being withdrawn
        // e.g. we have USDC + WBTC as collateral, end liquidationThreshold will be different depending on which asset we withdraw
        uint256 newTargetDebt = targetLTV.mul(newCollateral).div(MAX_BPS);
        if (newTargetDebt > totalDebtETH) {
            return 0;
        }
        return
            _fromETH(totalDebtETH.sub(newTargetDebt), address(investmentToken));
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
        if (!isWantIncentivised && !isInvestmentTokenIncentivised) {
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
    function _calculateMaxDebt()
        internal
        view
        returns (uint256 currentProtocolDebt, uint256 maxProtocolDebt)
    {
        // This function is used to calculate the maximum amount of debt that the protocol can take
        // to keep the cost of capital lower than the set acceptableCosts
        // This maxProtocolDebt will be used to decide if capital costs are acceptable or not
        // and to repay required debt to keep the rates below acceptable costs

        // Hack to avoid the stack too deep compiler error.
        SupportStructs.CalcMaxDebtLocalVars memory vars;
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
            acceptableCostsRay < irsVars.baseRate.add(irsVars.slope1)
        ) {
            // we solve Aave's Interest Rates equation for sub optimal utilisation rates
            // IR = BASERATE + SLOPE1 * CURRENT_UTIL_RATE / OPTIMAL_UTIL_RATE
            vars.targetUtilizationRate = (
                acceptableCostsRay.sub(irsVars.baseRate)
            )
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

    function _setIsWantIncentivised(bool _isWantIncentivised) internal {
        require(
            !_isWantIncentivised || // to avoid calling getIncentivesController if not incentivised
                address(aToken.getIncentivesController()) != address(0)
        );

        isWantIncentivised = _isWantIncentivised;
    }

    function _setIsInvestmentTokenIncentivised(
        bool _isInvestmentTokenIncentivised
    ) internal {
        require(
            !_isInvestmentTokenIncentivised || // to avoid calling getIncentivesController if not incentivised
                address(variableDebtToken.getIncentivesController()) !=
                address(0)
        );

        isInvestmentTokenIncentivised = _isInvestmentTokenIncentivised;
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

    function _buyInvestmentTokenWithWant(uint256 _amount) internal {
        if (_amount == 0) {
            return;
        }

        if (address(investmentToken) == address(want)) {
            return;
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
        _checkAllowance(address(router), path[0], _amount);

        router.swapTokensForExactTokens(
            _amount,
            type(uint256).max,
            path,
            address(this),
            now
        );
    }

    function _toETH(uint256 _amount, address asset)
        internal
        view
        returns (uint256)
    {
        if (_amount == 0) {
            return 0;
        }

        if (_amount == type(uint256).max) {
            return type(uint256).max;
        }

        // NOTE: 1:1
        if (address(asset) == address(WETH)) {
            return _amount;
        }

        return
            _amount.mul(_priceOracle().getAssetPrice(asset)).div(
                uint256(10)**uint256(IOptionalERC20(asset).decimals())
            );
    }

    function _fromETH(uint256 _amount, address asset)
        internal
        view
        returns (uint256)
    {
        if (_amount == 0) {
            return 0;
        }

        if (_amount == type(uint256).max) {
            return type(uint256).max;
        }

        // NOTE: 1:1
        if (address(asset) == address(WETH)) {
            return _amount;
        }

        return
            _amount
                .mul(uint256(10)**uint256(IOptionalERC20(asset).decimals()))
                .div(_priceOracle().getAssetPrice(asset));
    }

    // ----------------- INTERNAL SUPPORT GETTERS -----------------

    function _lendingPool() internal view returns (ILendingPool lendingPool) {
        lendingPool = ILendingPool(
            protocolDataProvider.ADDRESSES_PROVIDER().getLendingPool()
        );
    }

    function _priceOracle() internal view returns (IPriceOracle) {
        return
            IPriceOracle(
                protocolDataProvider.ADDRESSES_PROVIDER().getPriceOracle()
            );
    }

    function _incentivesController()
        internal
        view
        returns (IAaveIncentivesController)
    {
        if (isWantIncentivised) {
            return aToken.getIncentivesController();
        } else if (isInvestmentTokenIncentivised) {
            return variableDebtToken.getIncentivesController();
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
