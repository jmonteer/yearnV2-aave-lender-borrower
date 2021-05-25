import pytest
from brownie import chain, Wei, reverts, Contract, ZERO_ADDRESS


def test_emergency_exit_after_loss(
    vault, strategy, gov, link, link_whale, usdc, usdc_whale, yvUSDC
):
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    prev_balance = link.balanceOf(link_whale)

    link.approve(vault, 2 ** 256 - 1, {"from": link_whale})
    vault.deposit(Wei("1000 ether"), {"from": link_whale})
    strategy.harvest({"from": gov})

    # yvUSDC fails and we loss all our funds
    index = 0
    while yvUSDC.withdrawalQueue(index) != ZERO_ADDRESS:
        index = index + 1

    for i in range(0, index):
        strat = Contract(yvUSDC.withdrawalQueue(i))
        yvUSDC.revokeStrategy(strat, {"from": yvUSDC.governance()})
        strat.harvest({"from": yvUSDC.governance()})

    # gov rug pull 20%
    usdc.transfer(gov, usdc.balanceOf(yvUSDC) // 1.2, {"from": yvUSDC})
    lp = get_lending_pool()
    userDict = lp.getUserAccountData(strategy).dict()
    print_status(lp, strategy)
    assert userDict["totalDebtETH"] > 0

    # Changing the strategy params to take the loss
    strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),  # _targetLTVMultiplier
        strategy.warningLTVMultiplier(),  # _warningLTVMultiplier
        strategy.acceptableCostsRay(),  # _acceptableCostsRay
        0,  # _aaveReferral
        strategy.maxTotalBorrowIT(),  # _maxTotalBorrowIT
        strategy.isWantIncentivised(),  # _isWantIncentivised
        strategy.isInvestmentTokenIncentivised(),  # _isInvestmentTokenIncentivised
        False,  # leaveDebtBehind
        10_000,  # maxLoss
    )

    strategy.setEmergencyExit({"from": gov})
    strategy.harvest({"from": gov})

    assert vault.strategies(strategy).dict()["totalDebt"] == 0


def get_lending_pool():
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    return lp


def print_status(lp, strategy):
    userDict = lp.getUserAccountData(strategy).dict()
    currentDebtETH = userDict["totalDebtETH"]
    currentCollateralETH = userDict["totalCollateralETH"]
    currentLTV = currentDebtETH * 10_000 / currentCollateralETH
    print("Current Debt ETH", currentDebtETH / 1e18)
    print("Current Collateral ETH", currentCollateralETH / 1e18)
    print("CurrentLTV", currentLTV / 100, "%")
    print()
