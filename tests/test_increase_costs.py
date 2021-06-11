from brownie import chain, Wei, reverts, Contract


def test_increase_costs(
    vault, strategy, gov, token, token_whale, borrow_token, borrow_whale, yvault, vdToken, aToken
):
    if token.symbol() == "WETH":
        deposit_amount = 500 * (10 ** token.decimals())
    elif token.symbol() == "WBTC":
        deposit_amount = 50 * (10 ** token.decimals())
    elif token.symbol() == "DAI" or token.symbol() == "USDC":
        deposit_amount = 1_000_000 * (10 ** token.decimals())
    else: 
        deposit_amount = 100 * (10 ** token.decimals())

    assert vault.totalAssets() == 0
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(deposit_amount, {"from": token_whale})
    # whale has deposited 10btc in fixture
    lp = get_lending_pool()

    tx = strategy.harvest({"from": gov})
    chain.sleep(6 * 3600)
    chain.mine(1)

    # instead of increasing costs we reduce our acceptable costs
    currentCost = lp.getReserveData(borrow_token).dict()["currentVariableBorrowRate"]
    # put acceptablecosts just below currentCost
    acceptable = currentCost - 1e18

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
    # to compensate interest rate on borrowing
    if borrow_token.symbol() == "USDT" or borrow_token.symbol() == "USDC" or borrow_token.symbol() == "DAI":
        borrow_token.transfer(yvault, 25000 * (10 ** borrow_token.decimals()), {"from": borrow_whale})
    else: 
        borrow_token.transfer(yvault, 10 * (10 ** borrow_token.decimals()), {"from": borrow_whale})
    previousDebt = vdToken.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vdToken.balanceOf(strategy)

    assert (
        lp.getReserveData(borrow_token).dict()["currentVariableBorrowRate"]
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
    if borrow_token.symbol() == "USDT" or borrow_token.symbol() == "USDC" or borrow_token.symbol() == "DAI":
        borrow_token.transfer(yvault, 25000 * (10 ** borrow_token.decimals()), {"from": borrow_whale})
    else: 
        borrow_token.transfer(yvault, 10 * (10 ** borrow_token.decimals()), {"from": borrow_whale})
    previousDebt = vdToken.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vdToken.balanceOf(strategy)
    assert vdToken.balanceOf(strategy) == 0


def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    return lp
