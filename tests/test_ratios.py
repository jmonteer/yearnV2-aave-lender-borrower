import pytest
from brownie import chain, Wei, reverts, Contract


def test_lev_ratios(
    vault, strategy, gov, wmatic, wmatic_whale, dai, dai_whale, yvDAI, vddai, amwmatic, RELATIVE_APPROX
):
    lp = get_lending_pool()

    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10000 ether"), {"from": wmatic_whale})

    tx = strategy.harvest({"from": gov})

    targetLTV = strategy.targetLTVMultiplier()
    warningLTV = strategy.warningLTVMultiplier()

    print_status(lp, strategy)
    # should revert with ratios > 90%
    with reverts():
        strategy.setStrategyParams(
            9_001,
            9_001,
            strategy.acceptableCostsRay(),
            0,
            strategy.maxTotalBorrowIT(),
            strategy.isWantIncentivised(),
            strategy.isInvestmentTokenIncentivised(),
            strategy.leaveDebtBehind(),
            strategy.maxLoss(),
            {"from": strategy.strategist()},
        )
    # should revert if targetRatio > warningRatio
    with reverts():
        strategy.setStrategyParams(
            8_000,
            7_000,
            strategy.acceptableCostsRay(),
            0,
            strategy.maxTotalBorrowIT(),
            strategy.isWantIncentivised(),
            strategy.isInvestmentTokenIncentivised(),
            strategy.leaveDebtBehind(),
            strategy.maxLoss(),
            {"from": strategy.strategist()},
        )

    # we reduce the target to half and set ratios just below current ratios
    strategy.setStrategyParams(
        targetLTV / 2,
        targetLTV / 1.01,
        strategy.acceptableCostsRay(),
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )
    # to offset interest rates and be able to repay full debt (assuming we were able to generate profit before lowering acceptableCosts)
    dai.transfer(yvDAI, Wei("10000 ether"), {"from": dai_whale})
    previousDebt = vddai.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vddai.balanceOf(strategy)
    print_status(lp, strategy)

    print_status(lp, strategy)
    # we reduce the target to half and set target ratio = 0
    strategy.setStrategyParams(
        0,
        targetLTV / 3,  # trigger to set to rebalance
        strategy.acceptableCostsRay(),
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )
    # to offset interest rates and be able to repay full debt (assuming we were able to generate profit before lowering acceptableCosts)
    dai.transfer(yvDAI, Wei("10000 ether"), {"from": dai_whale})
    previousDebt = vddai.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert pytest.approx(vddai.balanceOf(strategy)/1e18, rel=RELATIVE_APPROX) == 0
    assert wmatic.balanceOf(strategy) == 0
    assert amwmatic.balanceOf(strategy) > 0  # want is deposited as collateral
    assert (
        amwmatic.balanceOf(strategy) == strategy.estimatedTotalAssets()
    )  # no debt, no investments

    print_status(lp, strategy)
    dai.transfer(yvDAI, Wei("1 ether"), {"from": dai_whale})

    vault.withdraw({"from": wmatic_whale})


def get_lending_pool():
    pd_provider = Contract("0x7551b5D2763519d4e37e8B81929D336De671d46d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    return lp


def print_status(lp, strategy):
    userDict = lp.getUserAccountData(strategy).dict()
    currentDebtETH = userDict["totalDebtETH"]
    currentCollateralETH = userDict["totalCollateralETH"]
    currentLTV = currentDebtETH * 10_000 / currentCollateralETH
    print("Current Debt ETH", currentDebtETH / 1e18)
    print("Current Collateral ETH", currentCollateralETH / 1e18)
    print("CurrentLTV", currentLTV / 100, "%")
    print()
