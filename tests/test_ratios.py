from brownie import chain, reverts, Contract


def test_lev_ratios(
    vault,
    strategy,
    gov,
    token,
    token_whale,
    borrow_token,
    borrow_whale,
    yvault,
    vdToken,
    aToken,
):
    lp = get_lending_pool()

    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(500_000 * (10 ** token.decimals()), {"from": token_whale})

    chain.sleep(1)
    strategy.harvest({"from": gov})

    targetLTV = strategy.targetLTVMultiplier()

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
            strategy.maxGasPriceToTend(),
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
            strategy.maxGasPriceToTend(),
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
        strategy.maxGasPriceToTend(),
        {"from": strategy.strategist()},
    )
    # to offset interest rates and be able to repay full debt (assuming we were able to generate profit before lowering acceptableCosts)
    borrow_token.transfer(
        yvault, 10_000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )
    previousDebt = vdToken.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vdToken.balanceOf(strategy)
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
        strategy.maxGasPriceToTend(),
        {"from": strategy.strategist()},
    )
    # to offset interest rates and be able to repay full debt (assuming we were able to generate profit before lowering acceptableCosts)
    borrow_token.transfer(
        yvault, 10000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )
    previousDebt = vdToken.balanceOf(strategy)
    strategy.harvest({"from": gov})
    print_status(lp, strategy)

    assert vdToken.balanceOf(strategy) == 0
    assert token.balanceOf(strategy) == 0
    assert aToken.balanceOf(strategy) > 0  # want is deposited as collateral
    # rounding
    # assert (
    #     strategy.estimatedTotalAssets()-aToken.balanceOf(strategy) < 3
    # )  # no debt, no investments
    print(f"TotalAssets:{strategy.estimatedTotalAssets()}")
    print(f"AToken: {aToken.balanceOf(strategy)}")
    borrow_token.transfer(
        yvault, 1000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )

    vault.withdraw({"from": token_whale})


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
