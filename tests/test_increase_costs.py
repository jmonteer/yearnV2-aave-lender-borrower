from brownie import chain, Wei, reverts, Contract


def test_increase_costs(
    vault, strategy, gov, wmatic, wmatic_whale, dai, dai_whale, yvDAI, vddai,
):
    deposit_amount = Wei("1_000 ether")
    assert vault.totalAssets() == 0
    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(deposit_amount, {"from": wmatic_whale})

    lp = get_lending_pool()

    tx = strategy.harvest({"from": gov})
    chain.sleep(6 * 3600)
    chain.mine(1)

    # instead of increasing costs we reduce our acceptable costs
    currentCost = lp.getReserveData(dai).dict()["currentVariableBorrowRate"]
    # put acceptablecosts just below currentCost
    acceptable = currentCost - 1e21

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        acceptable,
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )
    # to offset interest rates and be able to repay full debt (assuming we were able to generate profit before lowering acceptableCosts)
    dai.transfer(yvDAI, Wei("1 ether"), {"from": dai_whale})

    previousDebt = vddai.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vddai.balanceOf(strategy)

    # TODO: shouldn't this asset be the other way around?
    # assert (
    #     lp.getReserveData(dai).dict()["currentVariableBorrowRate"]
    #     < strategy.acceptableCostsRay()
    # )

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        0,  # set accceptable costs to 0
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )

    # to compensate interest rate on borrowing
    dai.transfer(yvDAI, Wei("1 ether"), {"from": dai_whale})
    # TODO: we do not have debt at this point
    # previousDebt = vddai.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vddai.balanceOf(strategy)
    assert vddai.balanceOf(strategy) == 0


def get_lending_pool():
    pd_provider = Contract("0x7551b5D2763519d4e37e8B81929D336De671d46d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    return lp
