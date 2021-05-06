import pytest
from brownie import chain, Wei, reverts, Contract


def test_change_yVault(vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH):
    lp = get_lending_pool()
    ic = get_incentives_controller(strategy)
    aToken = Contract(strategy.aToken())
    vdToken = Contract(strategy.variableDebtToken())
    stkAave = Contract(strategy.stkAave())
    vault_snx = Contract("0xF29AE508698bDeF169B89834F76704C3B205aedf")
    vault_susd = Contract("0xa5cA62D95D24A4a350983D5B8ac4EB8638887396")

    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    tx = strategy.harvest({"from": gov})

    chain.sleep(24 * 3600)
    chain.mine(1)

    # to offset interest rates and be able to repay full debt
    weth.transfer(yvETH, Wei("20_000 ether"), {"from": weth_whale})

    strategy.setYVault(vault_snx)

    assert vault_snx.balanceOf(strategy) == 0
    assert vault.balanceOf(strategy) == 0
    assert strategy.balanceOfDebt() == 0

    strategy.harvest({"from": gov})

    assert vault_snx.balanceOf(strategy) > 0


def get_incentives_controller(strat):
    atoken = Contract(strat.aToken())
    ic = Contract(atoken.getIncentivesController())
    return ic


def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    return lp


def print_debug(yvETH, strategy, lp):
    yvETH_balance = yvETH.balanceOf(strategy)
    yvETH_pps = yvETH.pricePerShare()
    totalDebtETH = lp.getUserAccountData(strategy).dict()["totalDebtETH"]

    print(f"yvETH balance {yvETH_balance} with pps {yvETH_pps}")
    yvETH_value = (yvETH_balance * yvETH_pps) / 1e18
    print(f"yvETH value {yvETH_value/1e18} vs {totalDebtETH/1e18}\n")
