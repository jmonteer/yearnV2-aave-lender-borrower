import pytest
from brownie import chain, Wei


def test_increase(vault, strategy, gov, wmatic, wmatic_whale, dai, dai_whale, yvDAI):
    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("20 ether"), {"from": wmatic_whale})
    vault.updateStrategyDebtRatio(strategy, 5_000, {"from": gov})

    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalDebt"] == Wei("10 ether")

    dai.transfer(yvDAI, Wei("20_000 ether"), {"from": dai_whale})
    tx = strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Go all the way up to 10k
    vault.updateStrategyDebtRatio(strategy, 10_000, {"from": gov})
    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalDebt"] >= Wei("20 ether")
    assert vault.strategies(strategy).dict()["totalLoss"] == 0


def test_decrease(vault, strategy, gov, wmatic, wmatic_whale):
    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("20 ether"), {"from": wmatic_whale})

    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalDebt"] == Wei("20 ether")

    tx = strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    vault.updateStrategyDebtRatio(strategy, 5_000, {"from": gov})
    tx = strategy.harvest({"from": gov})

    # 15 because it should be less than 20 but there is some profit.
    assert vault.strategies(strategy).dict()["totalDebt"] < Wei("15 ether")
    assert vault.strategies(strategy).dict()["totalLoss"] == 0
