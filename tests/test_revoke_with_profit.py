import pytest
from brownie import Wei


def test_revoke_with_profit(
    token,
    vault,
    strategy,
    wmatic_whale,
    gov,
    RELATIVE_APPROX,
    vddai,
    amwmatic,
    dai,
    dai_whale,
    yvDAI,
):
    token.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("30_000 ether"), {"from": wmatic_whale})
    strategy.harvest()

    # Send some profit to yvDAI
    dai.transfer(yvDAI, Wei("1_000 ether"), {"from": dai_whale})
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest()
    assert pytest.approx(vddai.balanceOf(strategy)/1e18, rel=RELATIVE_APPROX) == 0
    assert pytest.approx(amwmatic.balanceOf(strategy)/1e18, rel=RELATIVE_APPROX) == 0
    assert vault.strategies(strategy).dict()["totalGain"] > 0
    assert vault.strategies(strategy).dict()["totalDebt"] == 0
