import pytest
from brownie import chain, Wei, reverts, Contract


def test_change_yVault(
    vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH, awbtc, vdweth
):
    vault_snx = Contract("0xF29AE508698bDeF169B89834F76704C3B205aedf")
    snx = Contract(vault_snx.token())
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    tx = strategy.harvest({"from": gov})

    chain.sleep(24 * 3600)
    chain.mine(1)

    # to offset interest rates and be able to repay full debt
    weth.transfer(yvETH, Wei("20_000 ether"), {"from": weth_whale})

    strategy.setYVault(vault_snx, 0)

    assert vault_snx.balanceOf(strategy) == 0
    assert yvETH.balanceOf(strategy) == 0
    assert vdweth.balanceOf(strategy) == 0

    strategy.harvest({"from": gov})
    assert vault_snx.balanceOf(strategy) > 0

    # to offset interest rates and be able to repay full debt
    snx.transfer(
        vault_snx,
        Wei("10 ether"),
        {"from": "0xA1d7b2d891e3A1f9ef4bBC5be20630C2FEB1c470"},
    )
    strategy.setYVault(yvETH, 10_000)

    strategy.harvest({"from": gov})

    assert vault_snx.balanceOf(strategy) == 0
    assert yvETH.balanceOf(strategy) > 0
