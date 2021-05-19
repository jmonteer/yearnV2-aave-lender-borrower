import pytest
from brownie import chain, Wei, reverts


def test_migration(
    vault, strategy, Strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH, vdweth
):
    prev_balance = wbtc.balanceOf(wbtc_whale)
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    tx = strategy.harvest({"from": gov})
    weth.transfer(yvETH, Wei("20_000 ether"), {"from": weth_whale})
    tx = strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Deploy new Strategy and migrate
    strategy2 = gov.deploy(Strategy, vault, yvETH, True, True)
    # strategy migration is not implemented as debt is not transferrable, does not make much sense
    with reverts():
        vault.migrateStrategy(strategy, strategy2, {"from": gov})
