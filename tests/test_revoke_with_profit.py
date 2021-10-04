import pytest
from brownie import chain


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
    vault.deposit(500_000 * (10 ** token.decimals()), {"from": token_whale})

    chain.sleep(1)
    strategy.harvest({"from": gov})

    # Send some profit to yvault
    borrow_token.transfer(
        yvault, 20_000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})

    assert pytest.approx(vdToken.balanceOf(strategy) / 1e18, RELATIVE_APPROX) == 0
    assert pytest.approx(aToken.balanceOf(strategy) / 1e18, RELATIVE_APPROX) == 0
    assert vault.strategies(strategy).dict()["totalGain"] > 0
    assert vault.strategies(strategy).dict()["totalDebt"] <= 1
