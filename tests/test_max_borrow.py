import pytest


def test_max_borrow(vault, strategy, gov, token, token_whale, vdToken, borrow_token):
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(10 * (10 ** token.decimals()), {"from": token_whale})

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
    assert vdToken.balanceOf(strategy) == 0

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        strategy.acceptableCostsRay(),
        0,
        2_000 * (10 ** borrow_token.decimals()),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )
    strategy.harvest({"from": gov})
    assert vdToken.balanceOf(strategy) == 2_000 * (10 ** borrow_token.decimals())
