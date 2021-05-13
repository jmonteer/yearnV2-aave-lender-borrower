import pytest
from brownie import Wei

def test_revoke_strategy_from_vault(
    token, vault, strategy, wbtc_whale, gov, RELATIVE_APPROX, vdweth, awbtc, yvETH, weth, weth_whale
):
    amount = 10 * 1e8
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": wbtc_whale})
    vault.deposit(amount, {"from": wbtc_whale})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    vault.revokeStrategy(strategy.address, {"from": gov})
        
    # Send some profit to yvETH to compensate losses, so the strat is able to repay full amount
    weth.transfer(yvETH, Wei("1 ether"), {"from": weth_whale})

    strategy.harvest()
    assert vdweth.balanceOf(strategy) == 0
    assert awbtc.balanceOf(strategy) == 0
    assert pytest.approx(token.balanceOf(vault.address), rel=RELATIVE_APPROX) == amount


def test_revoke_strategy_from_strategy(
    token, vault, strategy, gov, wbtc_whale, RELATIVE_APPROX
):
    amount = 10 * 1e8
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": wbtc_whale})
    vault.deposit(amount, {"from": wbtc_whale})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    strategy.setEmergencyExit()
    strategy.harvest()
    assert pytest.approx(token.balanceOf(vault.address), rel=RELATIVE_APPROX) == amount
