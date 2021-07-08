import pytest
from brownie import chain, Wei, Contract, accounts, interface


def get_lp():
    pd_provider = Contract("0x7551b5D2763519d4e37e8B81929D336De671d46d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    return Contract(a_provider.getLendingPool())


def test_rate_above(
    vault, strategy, gov, wmatic, wmatic_whale, vddai,
):
    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("100 ether"), {"from": wmatic_whale})

    # This will increase the rate to > 75%
    increase_interest()

    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        0.75 * 1e27, # https://docs.aave.com/risk/liquidity-risk/borrow-interest-rate#dai-or-tusd
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        strategy.isInvestmentTokenIncentivised(),
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )

    strategy.harvest({"from": gov})
    assert vddai.balanceOf(strategy) == 0

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
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )

    strategy.harvest({"from": gov})
    assert vddai.balanceOf(strategy) > 0


def increase_interest():
    lp = get_lp()

    dai = Contract("0x8f3cf7ad23cd3cadbd9735aff958023239c6a063")
    amdai = interface.IAToken("0x27f8d03b3a2196956ed754badc28d73be8830a6e")

    whale = accounts.at("0x27f8d03b3a2196956ed754badc28d73be8830a6e", force=True)
    dai.approve(lp, 2 ** 256 - 1, {"from": whale})
    lp.deposit(dai, Wei("1 ether"), whale, 0, {"from": whale})

    liquidity = dai.balanceOf(amdai)
    to_move = liquidity - Wei("50_000 ether")
    dai.transfer(dai, to_move, {"from": amdai})

    # Withdraw 1 ether to update the rates
    lp.withdraw(dai, Wei("1 ether"), whale, {"from": whale})
