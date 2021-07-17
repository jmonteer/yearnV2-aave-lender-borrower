import pytest


def test_revoke_strategy_from_vault(
    token,
    vault,
    strategy,
    token_whale,
    gov,
    RELATIVE_APPROX,
    vdToken,
    aToken,
    yvault,
    borrow_token,
    borrow_whale,
):
    amount = 10 * (10 ** token.decimals())
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": token_whale})
    vault.deposit(amount, {"from": token_whale})
    strategy.harvest({"from": gov})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    vault.revokeStrategy(strategy.address, {"from": gov})

    # Send some profit to yvault to compensate losses, so the strat is able to repay full amount
    borrow_token.transfer(
        yvault, 1000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )

    strategy.harvest({"from": gov})
    assert pytest.approx(vdToken.balanceOf(strategy) / (10 ** vdToken.decimals()), rel=RELATIVE_APPROX) == 0
    assert pytest.approx(aToken.balanceOf(strategy) / (10 ** aToken.decimals()), rel=RELATIVE_APPROX) == 0
    assert pytest.approx(token.balanceOf(vault.address), rel=RELATIVE_APPROX) == amount


def test_revoke_strategy_from_strategy(
    token, vault, strategy, gov, token_whale, RELATIVE_APPROX
):
    amount = 10 * (10 ** token.decimals())
    # Deposit to the vault and harvest
    token.approve(vault.address, amount, {"from": token_whale})
    vault.deposit(amount, {"from": token_whale})
    strategy.harvest({"from": gov})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    strategy.setEmergencyExit({"from": gov})
    strategy.harvest({"from": gov})
    assert pytest.approx(token.balanceOf(vault.address), rel=RELATIVE_APPROX) == amount
