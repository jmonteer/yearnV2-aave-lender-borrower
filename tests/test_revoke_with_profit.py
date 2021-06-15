import pytest
from brownie import Wei


def test_revoke_with_profit(
    token,
    vault,
    strategy,
    token_whale,
    gov,
    RELATIVE_APPROX,
    vdToken,
    aToken,
    borrow_token,
    borrow_whale,
    yvault,
):
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(20 * (10 ** token.decimals()), {"from": token_whale})
    strategy.harvest()

    # Send some profit to yvault
    borrow_token.transfer(
        yvault, 20_000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest()

    assert vdToken.balanceOf(strategy) == 0
    assert aToken.balanceOf(strategy) == 0
    assert vault.strategies(strategy).dict()["totalGain"] > 0
    assert vault.strategies(strategy).dict()["totalDebt"] == 0
