import pytest
from brownie import Wei


def test_revoke_strategy_from_vault(
    token,
    vault,
    strategy,
    wmatic_whale,
    gov,
    RELATIVE_APPROX,
    vddai,
    amwmatic,
    yvDAI,
    dai,
    dai_whale,
):
    amount = Wei("10 ether")
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": wmatic_whale})
    vault.deposit(amount, {"from": wmatic_whale})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    vault.revokeStrategy(strategy.address, {"from": gov})

    # Send some profit to yvETH to compensate losses, so the strat is able to repay full amount
    dai.transfer(yvDAI, Wei("1 ether"), {"from": dai_whale})

    strategy.harvest()
    assert vddai.balanceOf(strategy) == 0
    assert amwmatic.balanceOf(strategy) == 0
    assert pytest.approx(token.balanceOf(vault.address), rel=RELATIVE_APPROX) == amount


def test_revoke_strategy_from_strategy(
    token, vault, strategy, gov, wmatic_whale, RELATIVE_APPROX
):
    amount = Wei("10 ether")
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": wmatic_whale})
    vault.deposit(amount, {"from": wmatic_whale})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    strategy.setEmergencyExit()
    strategy.harvest()
    assert pytest.approx(token.balanceOf(vault.address), rel=RELATIVE_APPROX) == amount
