import pytest
from brownie import Wei


def test_revoke_strategy_from_vault(
    token,
    vault,
    strategy,
    wbtc_whale,
    gov,
    RELATIVE_APPROX,
    vdweth,
    awbtc,
    weth,
    weth_whale,
    yvETH,
):
    token.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(20 * 1e8, {"from": wbtc_whale})
    strategy.harvest()

    # Send some profit to yvETH
    weth.transfer(yvETH, Wei("20_000 ether"), {"from": weth_whale})
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest()

    assert vault.strategies(strategy).dict()["totalGain"] > 0
    assert vault.strategies(strategy).dict()["totalDebt"] == 0
    assert vdweth.balanceOf(strategy) == 0
    assert awbtc.balanceOf(strategy) == 0
