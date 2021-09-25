import pytest
from brownie import chain, Wei, Contract, accounts, ZERO_ADDRESS


def get_lp():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    return Contract(a_provider.getLendingPool())


def test_rate_above_optimal(
    vault,
    strategy,
    gov,
    token,
    token_whale,
    vdToken,
    borrow_whale,
    yvault,
    borrow_token,
    aToken,
):
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(20 * (10 ** token.decimals()), {"from": token_whale})

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        1e26,
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        strategy.maxGasPriceToTend(),
        {"from": strategy.strategist()},
    )

    # This will increase the rate to > 100%
    increase_interest(borrow_token, borrow_whale)

    strategy.harvest({"from": gov})
    assert vdToken.balanceOf(strategy) == 0

    currentCost = (
        get_lp()
        .getReserveData(Contract(strategy.yVault()).token())
        .dict()["currentVariableBorrowRate"]
    )
    print(f"current rate: {currentCost/1e27}")

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        currentCost * 1.01,
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        strategy.maxGasPriceToTend(),
        {"from": strategy.strategist()},
    )

    strategy.harvest({"from": gov})
    assert vdToken.balanceOf(strategy) > 0


def increase_interest(bToken, whale):
    lp = get_lp()
    aBorrow = lp.getReserveData(bToken).dict()["aTokenAddress"]
    liquidity = bToken.balanceOf(aBorrow)
    to_move = liquidity * 0.9
    bToken.transfer(whale, to_move, {"from": aBorrow})  # to bToken to burn it randomly

    # Deposit 1 wei/unit to update the rates
    bToken.approve(lp, 2 ** 256 - 1, {"from": whale})
    lp.deposit(bToken, 1, whale, 0, {"from": whale})
