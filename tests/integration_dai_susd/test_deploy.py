import pytest
from brownie import chain, Contract, Wei


def test_deploy(
    yvDAI,
    yvSUSD,
    strategy,
    gov,
    dai,
    dai_whale,
    susd,
    susd_whale,
    vdsusd,
    RELATIVE_APPROX,
):
    dai.approve(yvDAI, 2 ** 256 - 1, {"from": dai_whale})
    yvDAI.deposit(Wei("100_000 ether"), {"from": dai_whale})

    # TODO: can we remove this sushi woes?
    susdEth = Contract("0xF1F85b2C54a2bD284B1cf4141D64fD171Bd85539")
    susdEth.sync({"from": gov})
    daiEth = Contract("0xC3D03e4F041Fd4cD388c549Ee2A29a9E5075882f")
    daiEth.sync({"from": gov})

    strategy.harvest({"from": gov})

    # After first investment sleep for a month
    chain.sleep(60 * 60 * 24 * 30)
    chain.mine(1)

    # Send some profit to yvault
    susd.transfer(
        yvSUSD,
        yvDAI.strategies(strategy).dict()["totalDebt"] * 0.05,
        {"from": susd_whale},
    )

    yvDAI.revokeStrategy(strategy, {"from": gov})
    tx = strategy.harvest({"from": gov})

    assert tx.events["Harvested"]["profit"] > 0
    assert tx.events["Harvested"]["debtPayment"] >= Wei("10 ether")

    data = yvDAI.strategies(strategy).dict()
    assert data["totalLoss"] == 0
    assert data["totalDebt"] == 0
    assert data["debtRatio"] == 0
    assert pytest.approx(yvSUSD.balanceOf(strategy) / 1e18, rel=RELATIVE_APPROX) == 0
    assert pytest.approx(vdsusd.balanceOf(strategy) / 1e18, rel=RELATIVE_APPROX) == 0
