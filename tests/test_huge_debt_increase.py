import pytest
from brownie import chain, Wei, Contract


def test_huge_debt(vault, strategy, gov, wmatic, wmatic_whale, dai, dai_whale, yvDAI):
    prev_balance = wmatic.balanceOf(wmatic_whale)
    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10 ether"), {"from": wmatic_whale})
    strategy.harvest({"from": gov})
    lp = get_lending_pool()

    prev_debt = lp.getUserAccountData(strategy).dict()["totalDebtETH"]
    print(f"T=0 totalDebtETH: {prev_debt}")

    # After first investment sleep for aproximately a year
    chain.sleep(60 * 60 * 24 * 365)
    chain.mine(1)
    new_debt = lp.getUserAccountData(strategy).dict()["totalDebtETH"]
    print(f"T=365 totalDebtETH: {new_debt}")
    assert new_debt > prev_debt

    # Test that there is no loss until withdrawal
    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalLoss"] == 0

    vault.withdraw(
        vault.balanceOf(wmatic_whale), wmatic_whale, 10_000, {"from": wmatic_whale}
    )

    print(f"diff {prev_balance-wmatic.balanceOf(wmatic_whale)}")
    assert prev_balance - wmatic.balanceOf(wmatic_whale) > 0


def get_lending_pool():
    pd_provider = Contract("0x7551b5D2763519d4e37e8B81929D336De671d46d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    return Contract(a_provider.getLendingPool())
