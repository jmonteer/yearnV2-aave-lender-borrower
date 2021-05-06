import pytest
from brownie import chain, Wei


def test_migration(
    vault, strategy, Strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH
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
    vault.migrateStrategy(strategy, strategy2, {"from": gov})

    assert strategy2.estimatedTotalAssets() > 0

    vault.withdraw(
        vault.balanceOf(wbtc_whale), wbtc_whale, 10_000, {"from": wbtc_whale}
    )
    assert wbtc.balanceOf(wbtc_whale) > prev_balance
