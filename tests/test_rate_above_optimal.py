import pytest
from brownie import chain, Wei, Contract, accounts, ZERO_ADDRESS


def get_lp():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    return Contract(a_provider.getLendingPool())


def test_rate_above_optimal(
    vault, strategy, gov, wbtc, wbtc_whale, vdweth, weth_whale, yvETH
):
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(20 * 1e8, {"from": wbtc_whale})

    # This will increase the rate to > 100%
    increase_interest()

    strategy.harvest({"from": gov})
    assert vdweth.balanceOf(strategy) == 0

    currentCost = (
        get_lp()
        .getReserveData(Contract(strategy.yVault()).token())
        .dict()["currentVariableBorrowRate"]
    )
    print(f"current rate: {currentCost/1e27}")

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        currentCost * 1.01,
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        {"from": strategy.strategist()},
    )

    strategy.harvest({"from": gov})
    assert vdweth.balanceOf(strategy) > 0


def increase_interest():
    lp = get_lp()
    weth = Contract("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")
    aeth = Contract("0x030bA81f1c18d280636F32af80b9AAd02Cf0854e")

    liquidity = weth.balanceOf(aeth)
    to_move = liquidity - Wei("500 ether")
    weth.transfer(ZERO_ADDRESS, to_move, {"from": aeth})

    # Withdraw 1 ether to update the rates
    whale = accounts.at("0x4deb3edd991cfd2fcdaa6dcfe5f1743f6e7d16a6", force=True)
    lp.withdraw(weth, Wei("1 ether"), whale, {"from": whale})
