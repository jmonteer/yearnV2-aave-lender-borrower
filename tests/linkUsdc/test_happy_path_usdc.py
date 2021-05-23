import pytest
from brownie import chain, Wei, reverts, Contract


def test_happy_path_usdc(
    vault, strategy, gov, link, link_whale, usdc, usdc_whale, yvUSDC
):
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    prev_balance = link.balanceOf(link_whale)

    link.approve(vault, 2 ** 256 - 1, {"from": link_whale})
    vault.deposit(Wei("1000 ether"), {"from": link_whale})

    print_debug(yvUSDC, strategy, lp)
    strategy.harvest({"from": gov})

    # With 1k link deposit, it should take at least a 2 eth value of USDC
    assert lp.getUserAccountData(strategy).dict()["totalDebtETH"] > Wei("2 ether")
    assert yvUSDC.balanceOf(strategy) > 0
    print_debug(yvUSDC, strategy, lp)

    # Sleep for 2 days
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Send some profit to yvUSDC
    usdc.transfer(yvUSDC, 10_000 * 1e6, {"from": usdc_whale})

    # TODO: check profits before and after
    strategy.harvest({"from": gov})
    print_debug(yvUSDC, strategy, lp)

    # We should have profit after getting some profit from yvUSDC
    assert vault.strategies(strategy).dict()["totalGain"] > 0
    assert vault.strategies(strategy).dict()["totalLoss"] == 0

    # Enough sleep for profit to be free
    chain.sleep(60 * 60 * 10)
    chain.mine(1)
    print_debug(yvUSDC, strategy, lp)

    vault.withdraw({"from": link_whale})
    assert link.balanceOf(link_whale) > prev_balance


def print_debug(yvUSDC, strategy, lp):
    yvUSDC_balance = yvUSDC.balanceOf(strategy)
    yvUSDC_pps = yvUSDC.pricePerShare()
    totalDebtETH = lp.getUserAccountData(strategy).dict()["totalDebtETH"]

    print(f"yvUSDC balance {yvUSDC_balance/1e6} with pps {yvUSDC_pps/1e6}")
    yvUSDC_value = (yvUSDC_balance * yvUSDC_pps) / 1e6
    print(f"yvUSDC value {yvUSDC_value/1e6} vs {totalDebtETH/1e18}\n")
