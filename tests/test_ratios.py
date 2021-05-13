from brownie import chain, Wei, reverts, Contract


def test_lev_ratios(
    vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH, vdweth, awbtc
):
    lp = get_lending_pool()

    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(100 * 1e8, {"from": wbtc_whale})

    tx = strategy.harvest({"from": gov})

    targetLTV = strategy.targetLTVMultiplier()
    warningLTV = strategy.warningLTVMultiplier()

    print_status(lp, strategy)
    # we reduce the target to half and set ratios just below current ratios
    strategy.setStrategyParams(
        targetLTV / 2,
        targetLTV / 1.01,
        strategy.acceptableCostsRay(),
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        {"from": strategy.strategist()},
    )
    # to offset interest rates and be able to repay full debt (assuming we were able to generate profit before lowering acceptableCosts)
    weth.transfer(yvETH, Wei("10000 ether"), {"from": weth_whale})
    previousDebt = vdweth.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vdweth.balanceOf(strategy)
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
        {"from": strategy.strategist()},
    )
    # to offset interest rates and be able to repay full debt (assuming we were able to generate profit before lowering acceptableCosts)
    weth.transfer(yvETH, Wei("10000 ether"), {"from": weth_whale})
    previousDebt = vdweth.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert vdweth.balanceOf(strategy) == 0
    assert wbtc.balanceOf(strategy) == 0
    assert awbtc.balanceOf(strategy) > 0  # want is deposited as collateral
    assert (
        awbtc.balanceOf(strategy) == strategy.estimatedTotalAssets()
    )  # no debt, no investments

    print_status(lp, strategy)
    weth.transfer(yvETH, Wei("1 ether"), {"from": weth_whale})

    vault.withdraw({"from": wbtc_whale})


def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
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
