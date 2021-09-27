from brownie import reverts


def test_set_max_loss_over_max_bps_should_revert(strategy, gov):
    maxBps = 10_000

    with reverts():
        strategy.setStrategyParams(
            strategy.targetLTVMultiplier(),
            strategy.warningLTVMultiplier(),
            strategy.acceptableCostsRay(),
            0,
            strategy.maxTotalBorrowIT(),
            strategy.isWantIncentivised(),
            False,
            strategy.leaveDebtBehind(),
            maxBps + 1,
            strategy.maxGasPriceToTend(),
            {"from": strategy.strategist()},
        )


def test_set_max_loss_to_max_bps_should_not_revert(strategy, gov):
    maxBps = 10_000

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        strategy.acceptableCostsRay(),
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        False,
        strategy.leaveDebtBehind(),
        maxBps,
        strategy.maxGasPriceToTend(),
        {"from": strategy.strategist()},
    )

    assert strategy.maxLoss() == maxBps


def test_set_max_loss_under_max_bps_should_not_revert(strategy, gov):
    maxBps = 10_000

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        strategy.acceptableCostsRay(),
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        False,
        strategy.leaveDebtBehind(),
        maxBps - 1,
        strategy.maxGasPriceToTend(),
        {"from": strategy.strategist()},
    )

    assert strategy.maxLoss() == maxBps - 1
