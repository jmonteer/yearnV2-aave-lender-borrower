import pytest


def test_max_borrow(vault, strategy, gov, token, token_whale, vdToken, borrow_token):
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(500_000 * (10 ** token.decimals()), {"from": token_whale})

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
        strategy.maxGasPriceToTend(),
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
        strategy.maxGasPriceToTend(),
        {"from": strategy.strategist()},
    )
    strategy.harvest({"from": gov})

    # Add both sides to account for rounding
    assert vdToken.balanceOf(strategy) > 1_999 * (10 ** borrow_token.decimals())
    assert vdToken.balanceOf(strategy) < 2_001 * (10 ** borrow_token.decimals())
