import pytest
from brownie import chain, Wei


def xtest_increase(vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH):
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(20 * 1e8, {"from": wbtc_whale})
    vault.updateStrategyDebtRatio(strategy, 5_000, {"from": gov})

    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalDebt"] == 10 * 1e8

    weth.transfer(yvETH, Wei("20_000 ether"), {"from": weth_whale})
    tx = strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Go all the way up to 10k
    vault.updateStrategyDebtRatio(strategy, 10_000, {"from": gov})
    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalDebt"] >= 20 * 1e8
    assert vault.strategies(strategy).dict()["totalLoss"] == 0


def test_decrease(vault, strategy, gov, wbtc, wbtc_whale):
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(20 * 1e8, {"from": wbtc_whale})

    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalDebt"] == 20 * 1e8

    tx = strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    vault.updateStrategyDebtRatio(strategy, 5_000, {"from": gov})
    tx = strategy.harvest({"from": gov})

    # 15 because it should be less than 20 but there is some profit.
    assert vault.strategies(strategy).dict()["totalDebt"] < 15 * 1e8
    assert vault.strategies(strategy).dict()["totalLoss"] == 0
