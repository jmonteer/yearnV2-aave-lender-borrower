import pytest


def test_revoke_strategy_from_vault(
    token, vault, strategy, wbtc_whale, gov, RELATIVE_APPROX
):
    amount = 10 * 1e8
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": wbtc_whale})
    vault.deposit(amount, {"from": wbtc_whale})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    vault.revokeStrategy(strategy.address, {"from": gov})
    strategy.harvest()
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
