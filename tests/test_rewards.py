import pytest
from brownie import chain, Wei, reverts, Contract


def test_rewards(vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH):
    lp = get_lending_pool()
    ic = get_incentives_controller(strategy)
    aToken = Contract(strategy.aToken())
    vdToken = Contract(strategy.variableDebtToken())
    stkAave = Contract(strategy.stkAave())

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

    previousStkAave = stkAave.balanceOf(strategy)
    previousAssets = strategy.estimatedTotalAssets()
    accumulatedRewards = ic.getRewardsBalance([vdToken, aToken], strategy)
    tx = strategy.harvest({"from": gov})

    assert stkAave.balanceOf(strategy) == accumulatedRewards
    assert strategy.harvestTrigger(0) == False
    assert strategy.estimatedTotalAssets() > previousAssets
    assert tx.events["Swap"][0]["amount0In"] == tx.events["Redeem"][0]["amount"]
    assert tx.events["Harvested"]["profit"] > 0

    # let harvest trigger during cooldown period
    chain.sleep(5 * 24 * 3600)  # 5 days
    chain.mine(1)

    tx = strategy.harvest({"from": gov})
    assert tx.events["Harvested"]


def test_rewards_on(strategist, keeper, vault, Strategy, gov, yvETH):
    vault_snx = Contract("0xF29AE508698bDeF169B89834F76704C3B205aedf")
    vault_susd = Contract("0xa5cA62D95D24A4a350983D5B8ac4EB8638887396")

    # it should deploy
    strategy = strategist.deploy(Strategy, vault_snx, vault_susd, False, False)

    with reverts():
        strategy.setIsWantIncentivised(True)

    with reverts():
        strategy.setIsInvestmentTokenIncentivised(True)


def get_incentives_controller(strat):
    atoken = Contract(strat.aToken())
    ic = Contract(atoken.getIncentivesController())
    return ic


def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    return lp
