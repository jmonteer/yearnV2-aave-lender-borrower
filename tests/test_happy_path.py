import pytest
from brownie import chain, Wei


def test_happy_path(vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH):
    prev_balance = wbtc.balanceOf(wbtc_whale)

    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    strategy.harvest({"from": gov})
    assert yvEth.balanceOf(strategy) > 0

    # Sleep for 2 days
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Send some profit to yvETH
    weth.transfer(Wei("20 ether"), yvETH, {"from": weth_whale})
    strategy.harvest({"from": gov})

    # We should have profit after getting some profit from yvETH
    assert vault.strategies(strategy).dict()["totalProfit"] > 0
    assert vault.strategies(strategy).dict()["totalLoss"] == 0

    # Enough sleep for profit to be free
    chain.sleep(60 * 60 * 10)
    chain.mine(1)

    vault.withdraw({"from": wbtc_whale})
    assert wbtc.balanceOf(wbtc_whale) > prev_balance
