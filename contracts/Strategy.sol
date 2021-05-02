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

    bool public isIncentivised;
    uint256 public acceptableCosts = 10e27; // TODO: check ray

    uint16 internal referral;
    uint16 internal DEFAULT_REFERRAL = 179;
    uint256 public targetLTVMultiplier = 6_000; // 60% of liquidation LTV
    uint256 public warningLTVMultiplier = 8_000; // 80% of liquidation LTV
    uint256 internal constant MAX_BPS = 10_000; // 100%

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
        referral = DEFAULT_REFERRAL;
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
            _balanceOfWant()
                .add(_balanceOfAToken()) // asset suplied as collateral
                .add(_investmentTokenToWant(_valueOfInvestment())) // current value of assets deposited in vault
                .sub(_investmentTokenToWant(_balanceOfDebt())); // liabilities
    }

    function balanceOfAToken() external view returns (uint256) {
        return _balanceOfAToken();
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

    function setAcceptableCosts(uint256 _acceptableCosts) external onlyAuthorized {
        acceptableCosts = _acceptableCosts;
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
        // TODO: Do stuff here to free up any returns back into `want`
        // NOTE: Return `_profit` which is value generated by all positions, priced in `want`
        // NOTE: Should try to free up at least `_debtOutstanding` of underlying position

        uint256 balanceInit = _balanceOfWant();
        // claim rewards from Aave's Liquidity Mining Program
        _claimRewards();
        // claim rewards from yVault
        _takeVaultProfit();
        uint256 balanceOfWant = _balanceOfWant();
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
    event Stats(uint256 totalCollateralETH,
        uint256 totalDebtETH,
        uint256 availableBorrowsETH,
        uint256 currentLiquidationThreshold,
        uint256 currentLTV,
        uint256 healthFactor 
        );
    function adjustPosition(uint256 _debtOutstanding) internal override {
        // TODO: Do something to invest excess `want` tokens (from the Vault) into your positions
        // NOTE: Try to adjust positions so that `_debtOutstanding` can be freed up on *next* harvest (not immediately)

        // TODO: check balance > _debtOutstanding
        // TODO: set availableCollateral
        uint256 wantBalance = _balanceOfWant();
        if (_debtOutstanding >= wantBalance) {
            return;
        }
        // TODO: check if there is any reason to now deposit collateral to aave
        uint256 amountToDeposit = wantBalance.sub(_debtOutstanding);
        _depositToAave(amountToDeposit);
        // _borrowInvestmentToken(1e18);
        // _depositInYVault();

        // return;
        // ------------ TODO --------------
        // TODO: get current lev ratio

        (uint256 totalCollateralETH,
        uint256 totalDebtETH,
        uint256 availableBorrowsETH,
        uint256 currentLiquidationThreshold,
        uint256 ltv,
        uint256 healthFactor 
        ) = _getAaveUserAccountData();
        emit Stats( totalCollateralETH,
         totalDebtETH,
         availableBorrowsETH,
         currentLiquidationThreshold,
         ltv,
         healthFactor 
        );
        uint256 currentLTV = totalDebtETH.mul(MAX_BPS).div(totalCollateralETH);
        uint256 targetLTV = _getTargetLTV(currentLiquidationThreshold); // 60% under liquidation Threshold
        uint256 warningLTV = _getWarningLTV(currentLiquidationThreshold); // 80% under liquidation Threshold
        emit Ratios(currentLTV, targetLTV, warningLTV, currentLiquidationThreshold);
        // decide in which range we are and act accordingly:
        // SUBOPTIMAL(borrow) (e.g. from 0 to 60% liqLTV)
        // HEALTHY(do nothing) (e.g. from 60% to 80% liqLTV)
        // UNHEALTHY(repay) (e.g. from 80% to 100% liqLTV)

        bool isAcceptableCosts = true;
        uint256 currentCost = _borrowingRate(0);
        // TODO: compare with real yVault APR
        isAcceptableCosts = currentCost <= acceptableCosts;

        if (currentLTV < targetLTV) {
            // SUBOPTIMAL RATIO
            // take on more debt
            uint256 targetDebtETH = totalCollateralETH.mul(targetLTV).div(MAX_BPS);
            uint256 amountToBorrowETH = targetDebtETH.sub(totalDebtETH);
            amountToBorrowETH = Math.min(availableBorrowsETH, amountToBorrowETH);
            emit Borrow(amountToBorrowETH);
            // only take this new debt if new costs are acceptable
            if(_borrowingRate(amountToBorrowETH) <= acceptableCosts) {
                uint256 amountToBorrowIT = _ethToInvestmentToken(amountToBorrowETH);
                _borrowInvestmentToken(amountToBorrowIT);
                _depositInYVault();
            }
        } else if (currentLTV > warningLTV || !isAcceptableCosts) {
            // UNHEALTHY RATIO
            // we repay debt to set it to targetLTV
            uint256 targetDebtETH = targetLTV.mul(totalCollateralETH).div(MAX_BPS);
            uint256 amountToRepayETH = totalDebtETH.sub(targetDebtETH);
            uint256 amountToRepayIT = _ethToInvestmentToken(amountToRepayETH);
            uint256 withdrawnIT = _withdrawFromYVault(amountToRepayIT); // we withdraw from investmentToken vault    
            _repayInvestmentTokenDebt(withdrawnIT); // we repay the investmentToken debt with Aave
        }
    }
    event Borrow(uint256 borrow);
    event Ratios(uint256 current, uint256 target,  uint256 warning, uint256 liq);
    function liquidatePosition(uint256 _amountNeeded)
        internal
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        // TODO: Do stuff here to free up to `_amountNeeded` from all positions back into `want`
        // NOTE: Maintain invariant `want.balanceOf(this) >= _liquidatedAmount`
        // NOTE: Maintain invariant `_liquidatedAmount + _loss <= _amountNeeded`
        
        uint256 balance = _balanceOfWant();
        // if we have enough want to take care of the liquidatePosition without actually liquidating positons
        if(balance >= _amountNeeded) {
            return (_amountNeeded, 0); 
        }

        // NOTE: amountNeeded is in want. amountToWithdraw is in want. 
        // NOTE: we need to repay using InvestmentToken
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
        if(_amountIT == 0) {
            return 0;
        }
        // no need to check allowance bc the contract == token
        uint256 balancePrior = _balanceOfInvestmentToken();
        uint256 sharesToWithdraw = Math.min(_investmentTokenToYShares(_amountIT), _balanceOfYShares());
        yVault.withdraw(sharesToWithdraw);
        return _balanceOfInvestmentToken().sub(balancePrior);
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

    // function harvestTrigger(uint256 callcost) external view returns (bool) {
    //     return _checkCooldown();
    // }

    // ----------------- INTERNAL FUNCTIONS SUPPORT -----------------
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
        if(amount == 0) {
            return;
        }
        emit Repayment(0, 0, _balanceOfInvestmentToken());

        (, uint256 debtInETH, , , , ) = _getAaveUserAccountData();

        uint256 balance = _balanceOfInvestmentToken();
        amount = Math.min(amount, balance);

        uint256 toRepayIT = Math.min(_ethToInvestmentToken(debtInETH), amount);
        _checkAllowance(address(_lendingPool()), address(investmentToken), toRepayIT);
        // TODO: check which are the units of the toRepayIT
        _lendingPool().repay(address(investmentToken), toRepayIT, 2, address(this));
    }

    function _depositInYVault() internal {
        _checkAllowance(
            address(yVault),
            address(investmentToken),
            _balanceOfInvestmentToken()
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
    event Repayment(uint256 repayIT, uint256 debt, uint256 it);
    //withdraw an amount including any want balance
    function _withdrawFromAave(uint256 amount) internal returns (uint256) {
        // We first repay whatever we need to repay to keep healthy ratios
        uint256 amountToRepayIT = _calculateAmountToRepay(amount);
        uint256 withdrawnIT = _withdrawFromYVault(amountToRepayIT); // we withdraw from investmentToken vault    
        emit Repayment(amountToRepayIT, _balanceOfDebt(), _balanceOfInvestmentToken());
        _repayInvestmentTokenDebt(withdrawnIT); // we repay the investmentToken debt with Aave
        uint256 balanceUnderlying = _balanceOfAToken();
        uint256 looseBalance = _balanceOfWant();
        uint256 total = balanceUnderlying.add(looseBalance);
        if (amount > total) {
            amount = total;
        }

        if (looseBalance >= amount) {
            return amount;
        }

        uint256 maxWithdrawal = Math.min(_maxWithdrawal(), want.balanceOf(address(aToken)));
        emit Repayment(amount.sub(looseBalance), _balanceOfDebt(), _maxWithdrawal());
        uint256 toWithdraw = Math.min(amount.sub(looseBalance), maxWithdrawal);
        if (toWithdraw > 0) {
            _checkAllowance(
                address(_lendingPool()),
                address(aToken),
                toWithdraw
            );
            _lendingPool().withdraw(address(want), toWithdraw, address(this));
        }

        looseBalance = _balanceOfWant();
        return looseBalance;
    }

    function _maxWithdrawal() internal view returns (uint256) {
        (uint256 totalCollateralETH, uint256 totalDebtETH, , , uint256 ltv, ) = _getAaveUserAccountData();
        uint256 minCollateralETH = totalDebtETH.mul(MAX_BPS).div(ltv);
        return _ethToWant(totalCollateralETH.sub(minCollateralETH));
    }

    function _calculateAmountToRepay(uint256 amount) internal view returns (uint256) {
        if(amount == 0) {
            return 0;
        }

        // we check if the collateral that we are withdrawing leaves us in a risky range, we then take action
        (uint256 totalCollateralETH, uint256 totalDebtETH, , uint256 currentLiquidationThreshold, , ) = _getAaveUserAccountData();

        uint256 amountToWithdrawETH = _wantToETH(amount);
        // calculate the collateral that we are leaving after withdrawing
        uint256 newCollateral = amountToWithdrawETH < totalCollateralETH ? totalCollateralETH.sub(amountToWithdrawETH) : 0;
        uint256 ltvAfterWithdrawal = newCollateral > 0 ? totalDebtETH.mul(MAX_BPS).div(newCollateral) : type(uint256).max;
        // check if the new LTV is in UNHEALTHY range
        // remember that if balance > _amountNeeded, ltvAfterWithdrawal == 0 (0 risk)
        // this is not true but the effect will be the same
        uint256 warningLTV = _getWarningLTV(currentLiquidationThreshold);

        if(ltvAfterWithdrawal <= warningLTV) {
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
        uint256 _debt = _balanceOfDebt();
        uint256 _valueInVault = _valueOfInvestment();
        if (_debt >= _valueInVault) {
            return;
        }

        uint256 profit = _valueInVault.sub(_debt);
        uint256 ySharesToWithdraw = _investmentTokenToYShares(profit);
        if (ySharesToWithdraw > 0) {
            yVault.withdraw(ySharesToWithdraw);
            _sellInvestmentForWant(_balanceOfInvestmentToken());
        }
    }

    // ----------------- INTERNAL CALCS -----------------
    function _borrowingRate(uint256 _additionalBorrow)
        public
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

    function _balanceOfWant() internal view returns (uint256) {
        return want.balanceOf(address(this));
    }

    function _balanceOfInvestmentToken() internal view returns (uint256) {
        return investmentToken.balanceOf(address(this));
    }

    function _balanceOfAToken() internal view returns (uint256) {
        return aToken.balanceOf(address(this));
    }

    function _balanceOfDebt() internal view returns (uint256) {
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

    function _getAaveUserAccountData() internal view returns (
            uint256 totalCollateralETH,
            uint256 totalDebtETH,
            uint256 availableBorrowsETH,
            uint256 currentLiquidationThreshold,
            uint256 ltv,
            uint256 healthFactor
        ) {
        return _lendingPool().getUserAccountData(address(this));
    }

    function _getTargetLTV(uint256 liquidationThreshold) internal view returns (uint256) {
        return liquidationThreshold.mul(targetLTVMultiplier).div(MAX_BPS);
    }

    function _getWarningLTV(uint256 liquidationThreshold) internal view returns (uint256) {
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

    function _investmentTokenToETH(uint256 amount)
        internal
        view
        returns (uint256)
    {
        // TODO: Make it generic to other investment tokens (currently 1:1)
        return amount;
    }

    function _wantToETH(uint256 _amount)
        internal 
        view
        returns (uint256)
    {
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

    function _ethToWant(uint256 _amount)
        internal 
        view
        returns (uint256)
    {
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

    function _ethToInvestmentToken(uint256 amount) internal view returns (uint256) {
        // TODO: Make it generic to other investment tokens (currently 1:1)
        return amount;
    }


    // ----------------- INTERNAL SUPPORT GETTERS -----------------

    function _getLiquidationLTV() internal view returns (uint256) {
        
    }

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
