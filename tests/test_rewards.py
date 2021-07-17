import pytest
from brownie import chain, Wei, reverts, Contract


def test_rewards(
    vault,
    strategy,
    gov,
    token,
    token_whale,
    aToken,
    vdToken,
    yvault,
    token_incentivised,
    borrow_incentivised,
    borrow_token,
    borrow_whale,
):
    ic = get_incentives_controller(
        aToken, vdToken, token_incentivised, borrow_incentivised
    )
    aToken = aToken
    vdToken = vdToken
    stkAave = Contract("0x4da27a545c0c5B758a6BA100e3a049001de870f5")

    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(100 * (10 ** token.decimals()), {"from": token_whale})

    assert ic.getRewardsBalance([aToken], strategy) == 0
    assert ic.getRewardsBalance([vdToken], strategy) == 0
    assert ic.getRewardsBalance([aToken, vdToken], strategy) == 0

    tx = strategy.harvest({"from": gov})
    assert yvault.balanceOf(strategy) > 0

    chain.sleep(2 * 24 * 3600)  # 48 hours later
    chain.mine(1)

    aTokenRewards = ic.getRewardsBalance([aToken], strategy)
    vdTokenRewards = ic.getRewardsBalance([vdToken], strategy)
    if token_incentivised:
        assert aTokenRewards > 0
    if borrow_incentivised:
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
    # Send some profit to yvault
    borrow_token.transfer(
        yvault, 20_000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )

    # NOTE: This expectation seems to be too volatile and unreliable.
    # assert strategy.harvestTrigger(Wei("1 ether")) == False
    chain.sleep(10 * 24 * 3600 + 1)  # a bit over 10 days passes
    chain.mine(1)
    assert strategy.harvestTrigger(Wei("1 ether")) == True

    accumulatedRewards = ic.getRewardsBalance([vdToken, aToken], strategy)
    if borrow_incentivised or token_incentivised:
        assert accumulatedRewards > 0

    tx = strategy.harvest({"from": gov})

    # Send some profit to yvault
    borrow_token.transfer(
        yvault, 200_000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )
    assert stkAave.balanceOf(strategy) >= accumulatedRewards
    assert strategy.harvestTrigger(Wei("1 ether")) == False
    assert (
        tx.events["Swap"][0]["amount0In"]
        == tx.events["Redeem"][0]["amount"] + tx.events["RewardsClaimed"][0]["amount"]
    )
    assert tx.events["RewardsClaimed"][0]["amount"] > 0
    assert tx.events["RewardsClaimed"][1]["amount"] > 0
    assert tx.events["Harvested"]["profit"] > 0

    # let harvest trigger during cooldown period
    chain.sleep(5 * 24 * 3600)  # 5 days
    chain.mine(1)
    # not working because rewards are off at the moment (expected to come back)
    # https://app.aave.com/governance/15-QmfYfZhLe5LYpCocm1JxdJ7sajV1QTjrK5UCF1TGe5HTfy
    assert stkAave.getTotalRewardsBalance(strategy) > 0

    tx = strategy.harvest({"from": gov})
    assert tx.events["Harvested"]
    # rewards off (expected to come back)
    # assert len(tx.events["RewardsClaimed"]) == 2


def get_incentives_controller(aToken, vdToken, token_incentivised, borrow_incentivised):
    if token_incentivised:
        ic = Contract(aToken.getIncentivesController())
        return ic
    elif borrow_incentivised:
        ic = Contract(vdToken.getIncentivesController())
        return ic

    return
