import pytest
from brownie import chain, Wei, reverts, Contract


def test_increase_costs(vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH):
    lp = get_lending_pool()
    po = get_price_oracle()
    ic = get_incentives_controller(strategy)
    aToken = Contract(strategy.aToken())
    vdToken = Contract(strategy.variableDebtToken())
    stkAave = Contract(strategy.stkAave())

    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    tx = strategy.harvest({'from': gov})
    chain.sleep(6 * 3600)
    chain.mine(1)

    # instead of increasing costs we reduce our acceptable costs
    currentCost = lp.getReserveData(strategy.investmentToken()).dict()['currentVariableBorrowRate']
    acceptable = strategy.acceptableCostsRay()
    # put acceptablecosts just below currentCost
    while(currentCost < acceptable):
        acceptable = acceptable - 1e22

    strategy.setAcceptableCosts(acceptable)
    
    # to offset interest rates and be able to repay full debt (assuming we were able to generate profit before lowering acceptableCosts)
    weth.transfer(yvETH, Wei("10000 ether"), {"from": weth_whale})
    
    previousDebt = strategy.balanceOfDebt()
    tx = strategy.harvest({'from': gov})
    assert previousDebt > strategy.balanceOfDebt()

    assert lp.getReserveData(strategy.investmentToken()).dict()['currentVariableBorrowRate'] < strategy.acceptableCostsRay()
    weth.transfer(yvETH, Wei("1 ether"), {"from": weth_whale})

    vault.withdraw({'from': wbtc_whale})

def get_incentives_controller(strat):
    atoken = Contract(strat.aToken())
    ic = Contract(atoken.getIncentivesController())
    return ic

def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    return lp

def get_price_oracle():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    po = Contract(a_provider.getPriceOracle())
    return po
