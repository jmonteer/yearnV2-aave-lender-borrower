import pytest
from brownie import chain, Contract, Wei

def test_deploy(vault, yvDAI, strategy, gov, wmatic, wmatic_whale, vddai, RELATIVE_APPROX):
    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("100000 ether"), {"from": wmatic_whale})

    strategy.harvest({"from": gov})

    # After first investment sleep for aproximately a year
    chain.sleep(60 * 60 * 24 * 365)
    chain.mine(1)

    vault.revokeStrategy(strategy)
    tx = strategy.harvest({"from": gov})
    
    data = vault.strategies(strategy).dict()
    assert data["totalLoss"] == 0
    assert data["totalDebt"] == 0
    assert data["debtRatio"] == 0
    assert yvDAI.balanceOf(strategy) == 0
    assert pytest.approx(vddai.balanceOf(strategy)/1e18, rel=RELATIVE_APPROX) == 0
    