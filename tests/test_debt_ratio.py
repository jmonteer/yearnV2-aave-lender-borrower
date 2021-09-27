import pytest
from brownie import chain


def test_increase(
    vault, strategy, gov, token, token_whale, borrow_token, borrow_whale, yvault
):
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(20 * (10 ** token.decimals()), {"from": token_whale})
    vault.updateStrategyDebtRatio(strategy, 5_000, {"from": gov})

    chain.sleep(1)
    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalDebt"] == 10 * (
        10 ** token.decimals()
    )

    borrow_token.transfer(
        yvault, 200 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )
    tx = strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Go all the way up to 10k
    vault.updateStrategyDebtRatio(strategy, 10_000, {"from": gov})

    chain.sleep(1)
    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalDebt"] >= 20 * (
        10 ** token.decimals()
    )
    assert vault.strategies(strategy).dict()["totalLoss"] == 0


def test_decrease(vault, strategy, gov, token, token_whale):
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(200_000 * (10 ** token.decimals()), {"from": token_whale})

    chain.sleep(1)
    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalDebt"] == 200_000 * (
        10 ** token.decimals()
    )

    chain.sleep(1)
    strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    vault.updateStrategyDebtRatio(strategy, 5_000, {"from": gov})
    strategy.harvest({"from": gov})

    # Should be less than 100_000 but there is some profit.
    assert vault.strategies(strategy).dict()["totalDebt"] < 100_001 * (
        10 ** token.decimals()
    )
    assert vault.strategies(strategy).dict()["totalLoss"] == 0
