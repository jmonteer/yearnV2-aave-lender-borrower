from brownie import chain, Wei, reverts


def test_migration_should_revert(
    vault,
    strategy,
    Strategy,
    gov,
    token,
    token_whale,
    borrow_token,
    borrow_whale,
    yvault,
    token_incentivised,
    borrow_incentivised,
    cloner,
    strategist,
):
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
    strategy2 = Strategy.at(
        cloner.cloneAaveLenderBorrower(
            vault,
            strategist,
            strategist,
            strategist,
            yvault,
            token_incentivised,
            borrow_incentivised,
            "name",
        ).return_value
    )

    vault.revokeStrategy(strategy, {"from": gov})
    strategy.harvest({"from": gov})

    with reverts():
        vault.migrateStrategy(strategy, strategy2, {"from": gov})
