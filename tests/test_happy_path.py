import pytest
from brownie import chain, Wei, reverts, Contract


def test_happy_path(vault, strategy, gov, wbtc, wbtc_whale, weth, weth_whale, yvETH):
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    prev_balance = wbtc.balanceOf(wbtc_whale)

    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})

    print_debug(yvETH, strategy, lp)
    tx = strategy.harvest({"from": gov})
    assert yvETH.balanceOf(strategy) > 0
    print_debug(yvETH, strategy, lp)

    # Sleep for 2 days
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Send some profit to yvETH
    weth.transfer(yvETH, Wei("20_000 ether"), {"from": weth_whale})

    # TODO: check profits before and after
    strategy.harvest({"from": gov})
    print_debug(yvETH, strategy, lp)

    # We should have profit after getting some profit from yvETH
    assert vault.strategies(strategy).dict()["totalGain"] > 0
    assert vault.strategies(strategy).dict()["totalLoss"] == 0

    # Enough sleep for profit to be free
    chain.sleep(60 * 60 * 10)
    chain.mine(1)
    print_debug(yvETH, strategy, lp)

    # why do we have losses? because of interests
    with reverts():
        vault.withdraw()

    # so we send profits
    weth.transfer(yvETH, Wei("1 ether"), {"from": weth_whale})


def print_debug(yvETH, strategy, lp):
    yvETH_balance = yvETH.balanceOf(strategy)
    yvETH_pps = yvETH.pricePerShare()
    totalDebtETH = lp.getUserAccountData(strategy).dict()["totalDebtETH"]

    print(f"yvETH balance {yvETH_balance} with pps {yvETH_pps}")
    yvETH_value = (yvETH_balance * yvETH_pps) / 1e18
    print(f"yvETH value {yvETH_value/1e18} vs {totalDebtETH/1e18}\n")
