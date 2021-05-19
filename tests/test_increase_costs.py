from brownie import chain, Wei, reverts, Contract


def test_increase_costs(
    vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH, vdweth, awbtc
):
    deposit_amount = 10 * 1e8
    assert vault.totalAssets() == 0
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(deposit_amount, {"from": wbtc_whale})
    # whale has deposited 10btc in fixture
    lp = get_lending_pool()

    tx = strategy.harvest({"from": gov})
    chain.sleep(6 * 3600)
    chain.mine(1)

    # instead of increasing costs we reduce our acceptable costs
    currentCost = lp.getReserveData(weth).dict()["currentVariableBorrowRate"]
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
    weth.transfer(yvETH, Wei("1 ether"), {"from": weth_whale})

    previousDebt = vdweth.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vdweth.balanceOf(strategy)

    assert (
        lp.getReserveData(weth).dict()["currentVariableBorrowRate"]
        < strategy.acceptableCostsRay()
    )

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
    weth.transfer(yvETH, Wei("1 ether"), {"from": weth_whale})
    previousDebt = vdweth.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vdweth.balanceOf(strategy)
    assert vdweth.balanceOf(strategy) == 0


def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    return lp
