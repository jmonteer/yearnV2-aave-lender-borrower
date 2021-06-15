import pytest
from brownie import chain, reverts, Contract


def test_happy_path(
    vault, strategy, gov, token, token_whale, borrow_token, borrow_whale, yvault
):
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    prev_balance = token.balanceOf(token_whale)

    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(10 * (10 ** token.decimals()), {"from": token_whale})

    print_debug(yvault, strategy, lp)
    tx = strategy.harvest({"from": gov})
    assert yvault.balanceOf(strategy) > 0
    print_debug(yvault, strategy, lp)

    # Sleep for 2 days
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Send some profit to yvault
    borrow_token.transfer(
        yvault, 20_000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )

    # TODO: check profits before and after
    strategy.harvest({"from": gov})
    print_debug(yvault, strategy, lp)

    # We should have profit after getting some profit from yvault
    assert vault.strategies(strategy).dict()["totalGain"] > 0
    assert vault.strategies(strategy).dict()["totalLoss"] == 0

    # Enough sleep for profit to be free
    chain.sleep(60 * 60 * 10)
    chain.mine(1)
    print_debug(yvault, strategy, lp)

    vault.withdraw({"from": token_whale})


def print_debug(yvault, strategy, lp):
    yvETH_balance = yvault.balanceOf(strategy)
    yvETH_pps = yvault.pricePerShare()
    totalDebtETH = lp.getUserAccountData(strategy).dict()["totalDebtETH"]

    print(f"yvault balance {yvETH_balance} with pps {yvETH_pps}")
    yvETH_value = (yvETH_balance * yvETH_pps) / 1e18
    print(f"yvault value {yvETH_value/1e18} vs {totalDebtETH/1e18}\n")
