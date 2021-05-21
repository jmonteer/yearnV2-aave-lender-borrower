import pytest
from brownie import chain, Wei, reverts, Contract


def test_clone(
    vault,
    strategy,
    strategist,
    rewards,
    keeper,
    gov,
    wbtc,
    awbtc,
    wbtc_whale,
    weth,
    weth_whale,
    yvETH,
):
    pd_provider = Contract("0x057835Ad21a177dbdd3090bB1CAE03EaCF78Fc6d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())
    vault_snx = Contract("0xF29AE508698bDeF169B89834F76704C3B205aedf")
    snx = Contract(vault_snx.token())
    snx_whale = "0xA1d7b2d891e3A1f9ef4bBC5be20630C2FEB1c470"
    clone_tx = strategy.clone(
        vault,
        strategist,
        rewards,
        keeper,
        vault_snx,
        True,
        False,
        "StrategyAaveLenderWBTCBorrowerSNX",
    )
    cloned_strategy = Contract.from_abi(
        "Strategy", clone_tx.events["Cloned"]["clone"], strategy.abi
    )

    cloned_strategy.setStrategyParams(
        strategy.targetLTVMultiplier(),
        strategy.warningLTVMultiplier(),
        strategy.acceptableCostsRay(),
        0,
        strategy.maxTotalBorrowIT(),
        strategy.isWantIncentivised(),
        False,  # snx is not incentivised
        strategy.leaveDebtBehind(),
        strategy.maxLoss(),
        {"from": strategy.strategist()},
    )

    vault.updateStrategyDebtRatio(strategy, 0, {"from": gov})
    vault.addStrategy(cloned_strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(10 * 1e8, {"from": wbtc_whale})
    strategy = cloned_strategy
    print_debug(vault_snx, strategy, lp)
    tx = strategy.harvest({"from": gov})
    assert vault_snx.balanceOf(strategy) > 0
    print_debug(vault_snx, strategy, lp)

    # Sleep for 2 days
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Send some profit to yvETH
    weth.transfer(snx, Wei("2000 ether"), {"from": snx_whale})

    # TODO: check profits before and after
    strategy.harvest({"from": gov})
    print_debug(vault_snx, strategy, lp)

    # We should have profit after getting some profit from yvETH
    assert vault.strategies(strategy).dict()["totalGain"] > 0
    assert vault.strategies(strategy).dict()["totalLoss"] == 0

    # Enough sleep for profit to be free
    chain.sleep(60 * 60 * 10)
    chain.mine(1)
    print_debug(vault_snx, strategy, lp)

    # why do we have losses? because of interests
    with reverts():
        vault.withdraw()

    # so we send profits
    snx.transfer(vault_snx, Wei("1000 ether"), {"from": snx_whale})
    vault.withdraw({"from": wbtc_whale})


def test_clone_of_clone(vault, strategist, rewards, keeper, strategy):
    vault_snx = Contract("0xF29AE508698bDeF169B89834F76704C3B205aedf")

    clone_tx = strategy.clone(
        vault,
        strategist,
        rewards,
        keeper,
        vault_snx,
        True,
        False,
        "StrategyAaveLenderWBTCBorrowerSNX",
    )
    cloned_strategy = Contract.from_abi(
        "Strategy", clone_tx.events["Cloned"]["clone"], strategy.abi
    )

    # should not clone a clone
    with reverts():
        cloned_strategy.clone(
            vault,
            strategist,
            rewards,
            keeper,
            vault_snx,
            True,
            False,
            "StrategyAaveLenderWBTCBorrowerSNX",
            {"from": strategist},
        )


def print_debug(yvSNX, strategy, lp):
    yvSNX_balance = yvSNX.balanceOf(strategy)
    yvSNX_pps = yvSNX.pricePerShare()
    totalDebtETH = lp.getUserAccountData(strategy).dict()["totalDebtETH"]

    print(f"yvSNX balance {yvSNX_balance} with pps {yvSNX_pps}")
    yvSNX_value = (yvSNX_balance * yvSNX_pps) / 1e18
    print(f"yvSNX value {yvSNX_value/1e18}SNX vs {totalDebtETH/1e18}ETH\n")
