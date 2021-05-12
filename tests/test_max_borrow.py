import pytest
from brownie import chain, Wei, Contract


def test_max_borrow(vault, strategy, gov, wbtc, wbtc_whale, vdweth):
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        strategy.acceptableCostsRay(),
        0,
        0,
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        {"from": strategy.strategist()},
    )
    strategy.harvest({"from": gov})
    assert vdweth.balanceOf(strategy) == 0

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        strategy.acceptableCostsRay(),
        0,
        Wei("2 ether"),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        {"from": strategy.strategist()},
    )
    strategy.harvest({"from": gov})
    assert vdweth.balanceOf(strategy) == Wei("2 ether")
