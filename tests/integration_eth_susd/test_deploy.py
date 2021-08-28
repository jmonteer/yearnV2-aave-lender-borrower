import pytest
from brownie import chain, Contract, Wei


def test_deploy(
    yvWETH,
    yvSUSD,
    strategy,
    gov,
    weth,
    weth_whale,
    susd,
    susd_whale,
    vdsusd,
    RELATIVE_APPROX,
):
    weth.approve(yvWETH, 2 ** 256 - 1, {"from": weth_whale})
    yvWETH.deposit(Wei("1_000 ether"), {"from": weth_whale})

    strategy.harvest({"from": gov})

    # After first investment sleep for a month
    chain.sleep(60 * 60 * 24 * 30)
    chain.mine(1)

    # Send some profit to yvault
    susd.transfer(
        yvSUSD, yvSUSD.totalDebt() * 0.05, {"from": susd_whale},
    )

    yvWETH.revokeStrategy(strategy, {"from": gov})
    tx = strategy.harvest({"from": gov})

    assert tx.events["Harvested"]["profit"] > 0
    assert tx.events["Harvested"]["debtPayment"] >= Wei("10 ether")

    data = yvWETH.strategies(strategy).dict()
    assert data["totalLoss"] == 0
    assert data["totalDebt"] == 0
    assert data["debtRatio"] == 0
    assert pytest.approx(yvSUSD.balanceOf(strategy) / 1e18, rel=RELATIVE_APPROX) == 0
    assert pytest.approx(vdsusd.balanceOf(strategy) / 1e18, rel=RELATIVE_APPROX) == 0
