import pytest
from brownie import chain, Wei, reverts, Contract


def test_happy_path(vault, strategy, gov, wmatic, wmatic_whale, dai, dai_whale, yvDAI):
    pd_provider = Contract("0x7551b5D2763519d4e37e8B81929D336De671d46d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    prev_balance = wmatic.balanceOf(wmatic_whale)

    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10 ether"), {"from": wmatic_whale})

    print_debug(yvDAI, strategy, lp)
    tx = strategy.harvest({"from": gov})
    assert yvDAI.balanceOf(strategy) > 0
    print_debug(yvDAI, strategy, lp)

    # Sleep for 2 days
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Send some profit to yvDAI
    dai.transfer(yvDAI, Wei("20_000 ether"), {"from": dai_whale})

    # TODO: check profits before and after
    strategy.harvest({"from": gov})
    print_debug(yvDAI, strategy, lp)

    # We should have profit after getting some profit from yvETH
    assert vault.strategies(strategy).dict()["totalGain"] > 0
    assert vault.strategies(strategy).dict()["totalLoss"] == 0

    # Enough sleep for profit to be free
    chain.sleep(60 * 60 * 10)
    chain.mine(1)
    print_debug(yvDAI, strategy, lp)

    vault.withdraw({"from": wmatic_whale})


def print_debug(yvDAI, strategy, lp):
    yvDAI_balance = yvDAI.balanceOf(strategy)
    yvDAI_pps = yvDAI.pricePerShare()
    totalDebtETH = lp.getUserAccountData(strategy).dict()["totalDebtETH"]

    print(f"yvDAI balance {yvDAI_balance} with pps {yvDAI_pps}")
    yvDAI_value = (yvDAI_balance * yvDAI_pps) / 1e18
    print(f"yvDAI value {yvDAI_value/1e18} vs {totalDebtETH/1e18}\n")
