import pytest
from brownie import chain, Wei, reverts, Contract


def test_rewards(vault, strategy, gov, wbtc, wbtc_whale, awbtc, vdweth, yvETH):
    ic = get_incentives_controller(awbtc)
    aToken = awbtc
    vdToken = vdweth
    stkAave = Contract("0x4da27a545c0c5B758a6BA100e3a049001de870f5")

    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    assert ic.getRewardsBalance([aToken], strategy) == 0
    assert ic.getRewardsBalance([vdToken], strategy) == 0
    assert ic.getRewardsBalance([aToken, vdToken], strategy) == 0

    tx = strategy.harvest({"from": gov})
    assert yvETH.balanceOf(strategy) > 0

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

    assert stkAave.stakersCooldowns(strategy) == 0
    tx = strategy.harvest({"from": gov})
    aTokenRewards = ic.getRewardsBalance([aToken], strategy)
    vdTokenRewards = ic.getRewardsBalance([vdToken], strategy)
    assert aTokenRewards == 0
    assert vdTokenRewards == 0
    assert stkAave.balanceOf(strategy) > 0
    assert stkAave.stakersCooldowns(strategy) != 0

    assert strategy.harvestTrigger(0) == False
    chain.sleep(10 * 24 * 3600 + 1)  # a bit over 10 days passes
    chain.mine(1)
    assert strategy.harvestTrigger(0) == True

    accumulatedRewards = ic.getRewardsBalance([vdToken, aToken], strategy)
    assert accumulatedRewards > 0

    tx = strategy.harvest({"from": gov})

    assert stkAave.balanceOf(strategy) >= accumulatedRewards
    assert strategy.harvestTrigger(0) == False
    assert tx.events["Swap"][0]["amount0In"] == tx.events["Redeem"][0]["amount"]
    assert tx.events["RewardsClaimed"][0]["amount"] > 0
    assert tx.events["Harvested"]["profit"] > 0

    # let harvest trigger during cooldown period
    chain.sleep(5 * 24 * 3600)  # 5 days
    chain.mine(1)
    # not working because rewards are off at the moment (expected to come back)
    # https://app.aave.com/governance/15-QmfYfZhLe5LYpCocm1JxdJ7sajV1QTjrK5UCF1TGe5HTfy
    # assert stkAave.getTotalRewardsBalance(strategy) > 0

    tx = strategy.harvest({"from": gov})
    assert tx.events["Harvested"]
    # rewards off (expected to come back)
    # assert len(tx.events["RewardsClaimed"]) == 2


def test_rewards_on(strategist, keeper, vault, Strategy, gov, yvETH):
    vault_snx = Contract("0xF29AE508698bDeF169B89834F76704C3B205aedf")
    vault_susd = Contract("0xa5cA62D95D24A4a350983D5B8ac4EB8638887396")

    # it should deploy
    strategy = strategist.deploy(Strategy, vault_snx, vault_susd, False, False)

    with reverts():
        strategy.setStrategyParams(
            strategy.targetLTVMultiplier(),
            strategy.warningLTVMultiplier(),
            strategy.acceptableCostsRay(),
            0,
            strategy.maxTotalBorrowIT(),
            True,
            True,
            strategy.leaveDebtBehind(),
            strategy.maxLoss(),
            {"from": strategy.strategist()},
        )

    with reverts():
        strategy.setStrategyParams(
            strategy.targetLTVMultiplier(),
            strategy.warningLTVMultiplier(),
            strategy.acceptableCostsRay(),
            0,
            strategy.maxTotalBorrowIT(),
            True,
            False,
            strategy.leaveDebtBehind(),
            strategy.maxLoss(),
            {"from": strategy.strategist()},
        )

    with reverts():
        strategy.setStrategyParams(
            strategy.targetLTVMultiplier(),
            strategy.warningLTVMultiplier(),
            strategy.acceptableCostsRay(),
            0,
            strategy.maxTotalBorrowIT(),
            False,
            True,
            strategy.leaveDebtBehind(),
            strategy.maxLoss(),
            {"from": strategy.strategist()},
        )


def get_incentives_controller(awbtc):
    ic = Contract(awbtc.getIncentivesController())
    return ic
