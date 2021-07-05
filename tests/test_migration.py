import pytest
from brownie import chain, Wei, reverts


def test_migration(
    vault, strategy, Strategy, gov, wmatic, wmatic_whale, dai, dai_whale, yvDAI, vddai
):
    prev_balance = wmatic.balanceOf(wmatic_whale)
    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10 ether"), {"from": wmatic_whale})

    tx = strategy.harvest({"from": gov})
    dai.transfer(yvDAI, Wei("20_000 ether"), {"from": dai_whale})
    tx = strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Deploy new Strategy and migrate
    strategy2 = gov.deploy(Strategy, vault, yvDAI, True, True, "name")
    # strategy migration is not implemented as debt is not transferrable, does not make much sense
    with reverts():
        vault.migrateStrategy(strategy, strategy2, {"from": gov})
