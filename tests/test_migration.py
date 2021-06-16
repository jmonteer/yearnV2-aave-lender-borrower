import pytest
from brownie import chain, Wei, reverts


def test_migration(
    vault,
    strategy,
    Strategy,
    gov,
    token,
    token_whale,
    borrow_token,
    borrow_whale,
    yvault,
    vdToken,
    token_incentivised,
    borrow_incentivised,
    cloner,
    strategist
):
    prev_balance = token.balanceOf(token_whale)
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(10 * (10 ** token.decimals()), {"from": token_whale})

    strategy.harvest({"from": gov})
    borrow_token.transfer(
        yvault, 20000 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )
    strategy.harvest({"from": gov})
    chain.sleep(60 * 60 * 24 * 2)
    chain.mine(1)

    # Deploy new Strategy and migrate
    strategy2 = Strategy.at(cloner.cloneAaveLenderBorrower(
        vault, strategist, strategist, strategist, yvault, token_incentivised, borrow_incentivised, "name"
    ).return_value)

    old_debt_ratio = vault.strategies(strategy).dict()["debtRatio"]
    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})
    vault.migrateStrategy(strategy, strategy2, {"from": gov})
    vault.updateStrategyDebtRatio(strategy2, old_debt_ratio, {"from": gov})
    strategy2.harvest({"from": gov})

    assert vault.strategies(strategy).dict()["totalDebt"] == 0
    assert vault.strategies(strategy2).dict()["totalDebt"] > 0
    assert vault.strategies(strategy2).dict()["debtRatio"] == old_debt_ratio
