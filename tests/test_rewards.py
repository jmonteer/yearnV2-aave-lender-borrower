import pytest
from brownie import chain, Wei, reverts, Contract


def test_rewards(vault, strategy, gov, wmatic, wmatic_whale, amwmatic, vddai, yvDAI):
    ic = get_incentives_controller(amwmatic)
    aToken = amwmatic
    vdToken = vddai

    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("1000 ether"), {"from": wmatic_whale})

    assert ic.getRewardsBalance([aToken], strategy) == 0
    assert ic.getRewardsBalance([vdToken], strategy) == 0
    assert ic.getRewardsBalance([aToken, vdToken], strategy) == 0

    tx = strategy.harvest({"from": gov})
    assert yvDAI.balanceOf(strategy) > 0

    chain.sleep(24 * 3600)  # 24 hours pass
    chain.mine(1)

    aTokenRewards = ic.getRewardsBalance([aToken], strategy)
    vdTokenRewards = ic.getRewardsBalance([vdToken], strategy)
    assert aTokenRewards > 0
    assert vdTokenRewards > 0
    assert (
        ic.getRewardsBalance([aToken, vdToken], strategy)
        == vdTokenRewards + aTokenRewards
    )

    tx = strategy.harvest({"from": gov})
    aTokenRewards = ic.getRewardsBalance([aToken], strategy)
    vdTokenRewards = ic.getRewardsBalance([vdToken], strategy)
    assert aTokenRewards == 0
    assert vdTokenRewards == 0

    assert strategy.harvestTrigger(0) == False
    chain.sleep(10 * 24 * 3600 + 1)  # a bit over 10 days passes
    chain.mine(1)
    assert strategy.harvestTrigger(0) == True

    accumulatedRewards = ic.getRewardsBalance([vdToken, aToken], strategy)
    assert accumulatedRewards > 0

    tx = strategy.harvest({"from": gov})

    assert strategy.harvestTrigger(0) == False
    assert tx.events["RewardsClaimed"][0]["amount"] > 0
    assert tx.events["Harvested"]["profit"] > 0


def get_incentives_controller(amwmatic):
    ic = Contract(amwmatic.getIncentivesController())
    return ic
