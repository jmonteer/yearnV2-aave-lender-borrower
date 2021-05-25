import pytest
from brownie import chain, Wei, reverts


def test_migration(
    vault, strategy, Strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH, vdweth
):
    prev_balance = wbtc.balanceOf(wbtc_whale)
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    strategy.harvest({"from": gov})
    weth.transfer(yvETH, Wei("20_000 ether"), {"from": weth_whale})
    strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Deploy new Strategy and migrate
    strategy2 = gov.deploy(Strategy, vault, yvETH, True, True, "name")

    old_debt_ratio = vault.strategies(strategy).dict()["debtRatio"]
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})
    vault.migrateStrategy(strategy, strategy2, {"from": gov})
    vault.updateStrategyDebtRatio(strategy2, old_debt_ratio, {"from": gov})
    strategy2.harvest({"from": gov})

    assert vault.strategies(strategy).dict()["totalDebt"] == 0
    assert vault.strategies(strategy2).dict()["totalDebt"] > 0
    assert vault.strategies(strategy2).dict()["debtRatio"] == old_debt_ratio
