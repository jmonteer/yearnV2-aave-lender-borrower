import pytest
from brownie import chain, Wei, Contract


def test_max_borrow(vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH):
    prev_balance = wbtc.balanceOf(wbtc_whale)
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    strategy.setMaxTotalBorrowIT(0, {"from": gov})
    strategy.harvest({"from": gov})
    assert strategy.balanceOfDebt() == 0

    strategy.setMaxTotalBorrowIT(Wei("2 ether"), {"from": gov})
    strategy.harvest({"from": gov})
    assert strategy.balanceOfDebt() == Wei("2 ether")