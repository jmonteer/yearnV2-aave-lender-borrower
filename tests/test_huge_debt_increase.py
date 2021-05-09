import pytest
from brownie import chain, Wei, Contract


def test_huge_debt(vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH):
    prev_balance = wbtc.balanceOf(wbtc_whale)
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})
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
        vault.balanceOf(wbtc_whale), wbtc_whale, 10_000, {"from": wbtc_whale}
    )

    print(f"diff {prev_balance-wbtc.balanceOf(wbtc_whale)}")
    assert prev_balance - wbtc.balanceOf(wbtc_whale) > 0


def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    return Contract(a_provider.getLendingPool())
