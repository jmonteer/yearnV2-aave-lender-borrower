import pytest
from brownie import chain, Contract, Wei


def test_deploy(
    yvDAI, yvSUSD, strategy, gov, dai, dai_whale, susd, susd_whale, vdsusd, RELATIVE_APPROX
):
    dai.approve(yvDAI, 2 ** 256 - 1, {"from": dai_whale})
    yvDAI.deposit(Wei("100000 ether"), {"from": dai_whale})

    strategy.harvest({"from": gov})

    # After first investment sleep for aproximately a year
    chain.sleep(60 * 60 * 24 * 365)
    chain.mine(1)

    # Send some profit to yvault
    susd.transfer(yvSUSD, 20_000 * (10 ** susd.decimals()), {"from": susd_whale})

    yvDAI.revokeStrategy(strategy)
    tx = strategy.harvest({"from": gov})

    data = yvDAI.strategies(strategy).dict()
    assert data["totalLoss"] == 0
    assert data["totalDebt"] == 0
    assert data["debtRatio"] == 0
    assert yvSUSD.balanceOf(strategy) == 0
    assert pytest.approx(vdsusd.balanceOf(strategy) / 1e18, rel=RELATIVE_APPROX) == 0
