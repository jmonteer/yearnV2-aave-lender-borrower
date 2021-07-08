import pytest
from brownie import chain, Wei, Contract


def test_max_borrow(vault, strategy, gov, wmatic, wmatic_whale, vddai):
    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10 ether"), {"from": wmatic_whale})

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        strategy.acceptableCostsRay(),
        0,
        0,
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )
    strategy.harvest({"from": gov})
    assert vddai.balanceOf(strategy) == 0

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        strategy.acceptableCostsRay(),
        0,
        Wei("2 ether"),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )
    strategy.harvest({"from": gov})
    assert vddai.balanceOf(strategy) == Wei("2 ether")
