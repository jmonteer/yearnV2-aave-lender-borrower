// SPDX-License-Identifier: AGPL-3.0
// Feel free to change the license, but this is what we use

// Feel free to change this version of Solidity. We support >=0.6.0 <0.7.0;
pragma solidity 0.6.12;
pragma experimental ABIEncoderV2;

// These are the core Yearn libraries
import {
    BaseStrategy,
    StrategyParams
} from "@yearnvaults/contracts/BaseStrategy.sol";
import "@openzeppelin/contracts/math/Math.sol";

import {
    SafeERC20,
    SafeMath,
    IERC20,
    Address
} from "@openzeppelin/contracts/token/ERC20/SafeERC20.sol";

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

// Import interfaces for many popular DeFi projects, or add your own!
//import "../interfaces/<protocol>/<Interface>.sol";

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
    
    // TODO: check this does not change
    IStakedAave public constant stkAave = IStakedAave(0x4da27a545c0c5B758a6BA100e3a049001de870f5);
    IAToken public aToken;
    IVault public yVault;
    IERC20 public investmentToken;
    IVariableDebtToken public variableDebtToken;
    address public constant WETH =
        address(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);

    // TODO: check if AAVE token can change
    address public constant AAVE =
        address(0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9);

    // TODO: check if protocol data provider can change
    IProtocolDataProvider public constant protocolDataProvider = IProtocolDataProvider(address(0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d));

    bool public isIncentivised;

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
        (address _aToken, , ) = protocolDataProvider.getReserveTokensAddresses(address(want));
        aToken = IAToken(_aToken);
        (, , address _variableDebtToken) = protocolDataProvider.getReserveTokensAddresses(address(investmentToken));
        variableDebtToken = IVariableDebtToken(_variableDebtToken);
        
        isIncentivised = _isIncentivised;
        referral = DEFAULT_REFERRAL;
    }

    // ----------------- PUBLIC VIEW FUNCTIONS -----------------

    function name() external view override returns (string memory) {
        // Add your own name here, suggestion e.g. "StrategyCreamYFI"
        return "StrategyAaveLenderBorrower";
    }

    function estimatedTotalAssets() public view override returns (uint256) {
        return _balanceOfWant()
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
        require(!_isIncentivised || address(aToken.getIncentivesController()) != address(0), "!aToken does not have incentives controller set up");
        isIncentivised = _isIncentivised;
    }

    function setReferralCode(uint16 _referral) external onlyAuthorized {
        require(_referral != 0, "!invalid referral code");
        referral = _referral;
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

        emit PrepareReturn(_debtPayment, _loss, _profit, _balanceOfWant());
    }

    event PrepareReturn (uint256 debtpayment, uint loss, uint profit, uint balance);

    function adjustPosition(uint256 _debtOutstanding) internal override {
        // TODO: Do something to invest excess `want` tokens (from the Vault) into your positions
        // NOTE: Try to adjust positions so that `_debtOutstanding` can be freed up on *next* harvest (not immediately)

        // TODO: check balance > _debtOutstanding
        // TODO: set availableCollateral
        uint256 wantBalance = _balanceOfWant();
        if(_debtOutstanding >= wantBalance){
            return;
        }
        // TODO: deposit 100% of available collateral
        uint256 amountToDeposit = wantBalance.sub(_debtOutstanding);
        _depositToAave(amountToDeposit);
        _borrowInvestmentToken(1e18);
        _depositInYVault();
        
        return;
        // ------------ TODO --------------
        // TODO: get current lev ratio
        uint256 currentLTV; 
        uint256 targetLTV;
        uint256 liquidationLTV;
        // decide in which range we are and act accordingly: 
            // SUBOPTIMAL(borrow) (from 0 to 40% LTV)
            // HEALTHY(do nothing) (from 40% to 60% LTV)
            // UNHEALTHY(repay) (from 60% to INF LTV)

        if(currentLTV > targetLTV) {
        // TODO: check if it is in SUBOPTIMAL range && borrowing costs are acceptable
            // take on more debt
            uint256 amountToBorrow = 0;
            _borrowInvestmentToken(amountToBorrow);
            _depositInYVault();
            // TODO: borrow investable asset
            // TODO: deposit in yVault
        } else if(currentLTV < liquidationLTV){

        }

        // TODO: check if it is in UNHEALTHY range OR borrowing costs are unacceptable
            // repay debt
            // TODO: withdraw from yVault
            // TODO: repay debt
    }

    function liquidatePosition(uint256 _amountNeeded)
        internal
        override
        returns (uint256 _liquidatedAmount, uint256 _loss)
    {
        // TODO: Do stuff here to free up to `_amountNeeded` from all positions back into `want`
        // NOTE: Maintain invariant `want.balanceOf(this) >= _liquidatedAmount`
        // NOTE: Maintain invariant `_liquidatedAmount + _loss <= _amountNeeded`
        uint256 balance = _balanceOfWant();
        uint256 LTVAfterWithdrawal = 0;
        uint256 amountToWithdraw = _amountNeeded;
        // if(balance < _amountNeeded) {
        //     amountToWithdraw = _amountNeeded.sub(balance);
            
        //     // calculate what the ratio is going to be
        //     uint256 aTokenBalance = _balanceOfAToken();
        //     uint256 collateral = aTokenBalance > amountToWithdraw ? aTokenBalance.sub(amountToWithdraw) : 0;
        //     uint256 debt = _balanceOfDebt();
        //     LTVAfterWithdrawal = collateral > 0 ? debt.mul(10 ** yVault.decimals()).div(collateral) : 999999999999; // TODO: check inf
        // }

        // if(LTVAfterWithdrawal > _getWarningLTV()) {
        //     // UNHEALTHY RANGE
        //         uint256 amountToRepay = amountToWithdraw;
        //         _withdrawFromYVault(amountToRepay);
        //         _repayInvestmentTokenDebt(amountToWithdraw);
        // }
        
        _withdrawFromAave(amountToWithdraw);

        uint256 totalAssets = _balanceOfWant();
        if (_amountNeeded > totalAssets) {
            _liquidatedAmount = totalAssets;
            _loss = _amountNeeded.sub(totalAssets);
        } else {
            _liquidatedAmount = _amountNeeded;
        }
    }

    // NOTE: Can override `tendTrigger` and `harvestTrigger` if necessary

    function prepareMigration(address _newStrategy) internal override {
        // TODO: Transfer any non-`want` tokens to the new strategy
        // NOTE: `migrate` will automatically forward all `want` in this strategy to the new one
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
        amount = Math.min(amount, _maxBorrowableInWant());
        if(amount == 0) {
            return;
        }
        _lendingPool().borrow(address(investmentToken), amount, 2, referral, address(this));
    }

    function _repayInvestmentTokenDebt(uint256 amount) internal {
        ILendingPool lp = _lendingPool();
        
        (, uint256 debtInETH, , , , ) =  lp.getUserAccountData(address(this));
        
        uint256 balance = _balanceOfInvestmentToken();
        amount = Math.min(amount, balance);

        uint256 toRepay = Math.min(debtInETH, _investmentTokenToETH(amount));
        // TODO: check which are the units of the repayAmount
        lp.repay(address(investmentToken), toRepay, 2, address(this));
    }

    function _investmentTokenToETH(uint256 amount) internal view returns (uint256) {
        // TODO: Make it generic to other investment tokens (currently 1:1)
        return amount;
    }

    function _ethToInvestToken(uint256 amount) internal view returns (uint256) {
        // TODO: Make it generic to other investment tokens (currently 1:1)
        return amount;
    }

    function _depositInYVault() internal {
        _checkAllowance(address(yVault), address(investmentToken), _balanceOfInvestmentToken());
        yVault.deposit();
    }

    function _claimRewards() internal {
        if(isIncentivised) {
            // redeem AAVE from stkAave
            uint256 stkAaveBalance = IERC20(address(stkAave)).balanceOf(address(this));
            if(stkAaveBalance > 0 && _checkCooldown()) {
                stkAave.redeem(address(this), stkAaveBalance);
            }

            // sell AAVE for want
            uint256 aaveBalance = IERC20(AAVE).balanceOf(address(this));
            _sellAAVEForWant(aaveBalance);

            // claim rewards
            address[] memory assets = new address[](1);
            assets[0] = address(aToken);
            uint256 pendingRewards = _incentivesController().getRewardsBalance(assets, address(this));
            if(pendingRewards > 0) {
                _incentivesController().claimRewards(assets, pendingRewards, address(this));
            }

            // request start of cooldown period
            if(IERC20(address(stkAave)).balanceOf(address(this)) > 0) {
                stkAave.cooldown();
            }
        }
    }

    //withdraw an amount including any want balance
    function _withdrawFromAave(uint256 amount) internal returns (uint256) {
        uint256 balanceUnderlying = _balanceOfAToken();
        uint256 looseBalance = _balanceOfWant();
        uint256 total = balanceUnderlying.add(looseBalance);

        if (amount > total) {
            amount = total;
        }

        if (looseBalance >= amount) {
            return amount;
        }

        uint256 liquidity = want.balanceOf(address(aToken));
        uint256 toWithdraw = Math.min(amount.sub(looseBalance), liquidity);
        if(toWithdraw > 0) {
            _checkAllowance(address(_lendingPool()), address(aToken), toWithdraw);
            _lendingPool().withdraw(address(want), toWithdraw, address(this));
        }
    
        looseBalance = _balanceOfWant();
        return looseBalance;
    }

    function _depositToAave(uint256 amount) internal {
        if(amount == 0) {
            return;
        }

        ILendingPool lp = _lendingPool();
        _checkAllowance(address(lp), address(want), amount);
        lp.deposit(address(want), amount, address(this), referral);
    }

    function _checkCooldown() internal view returns (bool) {
        if(!isIncentivised) {
            return false;
        }

        uint256 cooldownStartTimestamp = IStakedAave(stkAave).stakersCooldowns(address(this));
        uint256 COOLDOWN_SECONDS = IStakedAave(stkAave).COOLDOWN_SECONDS();
        uint256 UNSTAKE_WINDOW = IStakedAave(stkAave).UNSTAKE_WINDOW();
        if(block.timestamp >= cooldownStartTimestamp.add(COOLDOWN_SECONDS)) {
            return block.timestamp.sub(cooldownStartTimestamp.add(COOLDOWN_SECONDS)) <= UNSTAKE_WINDOW || cooldownStartTimestamp == 0;
        }

        return false;
    }

    function _checkAllowance(address _contract, address _token, uint256 _amount) internal {
        if (
            IERC20(_token).allowance(address(this), _contract) < _amount
        ) {
            IERC20(_token).safeApprove(_contract, 0);
            IERC20(_token).safeApprove(_contract, type(uint256).max);
        }
    }

    function _sellAAVEForWant(uint256 _amount) internal {
        if (_amount == 0) {
            return;
        }

        address[] memory path;

        if(address(want) == address(WETH)) {
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

        router.swapExactTokensForTokens(
            _amount,
            0,
            path,
            address(this),
            now
        );
    }

    function _sellInvestmentForWant(uint256 _amount) internal {
        if (_amount == 0) {
            return;
        }

        // NOTE: 1:1
        if(address(want) == address(investmentToken)) {
            return;
        }

        address[] memory path;
        if(address(want) == address(WETH) || address(investmentToken) == address(WETH)) {
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

        router.swapExactTokensForTokens(
            _amount,
            0,
            path,
            address(this),
            now
        );
    }

    function _takeVaultProfit() internal {
        // TODO: implement
        uint256 _debt = _balanceOfDebt();
        uint256 _valueInVault = _valueOfInvestment();
        if(_debt >= _valueInVault) {
            return;
        }

        uint256 profit = _valueInVault.sub(_debt);
        uint256 ySharesToWithdraw = _investmentToYShares(profit);
        if(ySharesToWithdraw > 0) {
            yVault.withdraw(ySharesToWithdraw);
            _sellInvestmentForWant(_balanceOfInvestmentToken());
        }
    }
    // ----------------- INTERNAL CALCS -----------------
    function _maxBorrowableInWant() internal view returns (uint256) {
        (, , uint256 availableBorrowsETH, , , ) = _lendingPool().getUserAccountData(address(this));
        // TODO: check liquidity aave + convert to want
        return availableBorrowsETH;
    }

    function _AAVEtoWant(uint256 _amount) internal view returns (uint256) {
        if(_amount == 0) {
            return 0;
        }

        address[] memory path;

        if(address(want) == address(WETH)) {
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

    function _investmentTokenToWant(uint256 _amount) internal view returns (uint256) {
        if(_amount == 0) {
            return 0;
        }

        // NOTE: 1:1
        if(address(want) == address(investmentToken)) {
            return _amount;
        }

        address[] memory path;
        if(address(want) == address(WETH) || address(investmentToken) == address(WETH)) {
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
        (, uint256 ethDebt, , , , ) = _lendingPool().getUserAccountData(address(this));
        return _ethToInvestToken(ethDebt);
    }

    function _balanceOfYShares() internal view returns (uint256) {
        return yVault.balanceOf(address(this));
    }

    function _getPricePerYShare() internal view returns (uint256) {
        return yVault.pricePerShare();
    }

    function _valueOfInvestment() internal view returns (uint256) {
        return _balanceOfYShares().mul(_getPricePerYShare()).div(10 ** yVault.decimals());
    }

    function _investmentToYShares(uint256 amount) internal view returns (uint256) {
        return amount.mul(10 ** yVault.decimals()).div(_getPricePerYShare());
    }

    function _getCurrentLTV() internal view returns (uint256) {
        // TODO: get current debt
        // TODO: get current collateral
        uint256 _debt; 
        uint256 _collateral;
        return _debt.mul(10 ** yVault.decimals()).div(_collateral); // same decimals that want
    }

    function _getTargetLTV() internal view returns (uint256) {
        return _getLiquidationLTV().mul(targetLTVMultiplier).div(MAX_BPS);
    }

    function _getWarningLTV() internal view returns (uint256) {
        return _getLiquidationLTV().mul(warningLTVMultiplier).div(MAX_BPS);
    }
    // ----------------- INTERNAL SUPPORT GETTERS -----------------

    function _getLiquidationLTV() internal view returns (uint256) {

    }

    function _lendingPool() internal view returns (ILendingPool lendingPool) {
        lendingPool = ILendingPool(protocolDataProvider.ADDRESSES_PROVIDER().getLendingPool());
    }

    function _incentivesController() internal view returns (IAaveIncentivesController) {
        if(isIncentivised) {
            return aToken.getIncentivesController();
        } else {
            return IAaveIncentivesController(0);
        }
    }


    // Override this to add all tokens/tokenized positions this contract manages
    // on a *persistent* basis (e.g. not just for swapping back to want ephemerally)
    // NOTE: Do *not* include `want`, already included in `sweep` below
    //
    // Example:
    //
    //    function protectedTokens() internal override view returns (address[] memory) {
    //      address[] memory protected = new address[](3);
    //      protected[0] = tokenA;
    //      protected[1] = tokenB;
    //      protected[2] = tokenC;
    //      return protected;
    //    }
    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {}
}
