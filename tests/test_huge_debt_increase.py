import pytest
from brownie import chain, Contract


def test_huge_debt(vault, strategy, gov, token, token_whale, borrow_token, borrow_whale, yvault):
    prev_balance = token.balanceOf(token_whale)
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(10 * (10**token.decimals()), {"from": token_whale})
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
        vault.balanceOf(token_whale), token_whale, 10_000, {"from": token_whale}
    )

    print(f"diff {prev_balance-token.balanceOf(token_whale)}")
    assert prev_balance - token.balanceOf(token_whale) > 0


def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    return Contract(a_provider.getLendingPool())
