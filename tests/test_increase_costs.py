from brownie import chain, Wei, reverts, Contract


def test_increase_costs(
    vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH, vdweth, awbtc
):
    lp = get_lending_pool()

    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(100 * 1e8, {"from": wbtc_whale})

    tx = strategy.harvest({"from": gov})
    chain.sleep(6 * 3600)
    chain.mine(1)

    # instead of increasing costs we reduce our acceptable costs
    currentCost = lp.getReserveData(weth).dict()["currentVariableBorrowRate"]
    # put acceptablecosts just below currentCost
    acceptable = currentCost - 1e21

    strategy.setAcceptableCosts(acceptable)

    # to offset interest rates and be able to repay full debt (assuming we were able to generate profit before lowering acceptableCosts)
    weth.transfer(yvETH, Wei("10000 ether"), {"from": weth_whale})

    previousDebt = vdweth.balanceOf(strategy)
    tx = strategy.harvest({"from": gov})
    assert previousDebt > vdweth.balanceOf(strategy)

    assert (
        lp.getReserveData(weth).dict()["currentVariableBorrowRate"]
        < strategy.acceptableCostsRay()
    )
    weth.transfer(yvETH, Wei("1 ether"), {"from": weth_whale})

    vault.withdraw({"from": wbtc_whale})


def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    return lp
