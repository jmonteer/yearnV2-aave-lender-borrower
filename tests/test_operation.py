from brownie import chain, reverts
import pytest


def test_operation(token, vault, token_whale, strategy, strategist, RELATIVE_APPROX):
    user_balance_before = token.balanceOf(token_whale)

    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(500_000 * (10 ** token.decimals()), {"from": token_whale})
    amount = 500_000 * (10 ** token.decimals())
    # Deposit to the vault
    assert token.balanceOf(vault.address) == amount

    # harvest
    chain.sleep(1)
    strategy.harvest({"from": strategist})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # tend()
    strategy.tend({"from": strategist})

    # withdrawal
    vault.withdraw({"from": token_whale})
    assert (
        pytest.approx(token.balanceOf(token_whale), rel=RELATIVE_APPROX)
        == user_balance_before
    )


def test_emergency_exit(
    token, vault, strategy, token_whale, strategist, RELATIVE_APPROX
):
    # Deposit to the vault
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(500_000 * (10 ** token.decimals()), {"from": token_whale})
    amount = 500_000 * (10 ** token.decimals())

    chain.sleep(1)
    strategy.harvest({"from": strategist})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # set emergency and exit
    strategy.setEmergencyExit({"from": strategist})
    strategy.harvest({"from": strategist})
    assert strategy.estimatedTotalAssets() < amount


def test_profitable_harvest(
    token,
    vault,
    strategy,
    token_whale,
    strategist,
    RELATIVE_APPROX,
    chain,
    borrow_token,
    borrow_whale,
    yvault,
):
    # Deposit to the vault
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(500_000 * (10 ** token.decimals()), {"from": token_whale})
    amount = 500_000 * (10 ** token.decimals())
    assert token.balanceOf(vault.address) == amount

    # Harvest 1: Send funds through the strategy
    chain.sleep(1)
    strategy.harvest({"from": strategist})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # increase rewards, lending interest and borrowing interests
    chain.sleep(50 * 24 * 3600)
    chain.mine(1)

    strategy.harvest({"from": strategist})  # to claim and start cooldown

    chain.sleep(10 * 24 * 3600 + 1)  # sleep during cooldown
    chain.mine(1)

    borrow_token.transfer(yvault, yvault.totalAssets() * 0.005, {"from": borrow_whale})
    before_pps = vault.pricePerShare()
    # Harvest 2: Realize profit
    chain.sleep(1)
    strategy.harvest({"from": strategist})
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)

    assert vault.totalAssets() > amount
    assert vault.pricePerShare() > before_pps


def test_change_debt(
    gov, token, vault, token_whale, strategy, user, strategist, RELATIVE_APPROX
):
    # Deposit to the vault and harvest
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(500_000 * (10 ** token.decimals()), {"from": token_whale})
    vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})

    chain.sleep(1)
    strategy.harvest({"from": gov})
    amount = 500_000 * (10 ** token.decimals())
    half = int(amount / 2)

    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == half

    vault.updateStrategyDebtRatio(strategy.address, 10_000, {"from": gov})
    strategy.harvest({"from": gov})
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # In order to pass this tests, you will need to implement prepareReturn.
    # TODO: uncomment the following lines.
    # vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})
    # strategy.harvest()
    # assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == half


def test_sweep(gov, vault, strategy, token, token_whale, borrow_whale, borrow_token):
    # Strategy want token doesn't work
    token.transfer(strategy, 500_000 * (10 ** token.decimals()), {"from": token_whale})
    assert token.address == strategy.want()
    assert token.balanceOf(strategy) > 0
    with reverts("!want"):
        strategy.sweep(token, {"from": gov})

    # Vault share token doesn't work
    with reverts("!shares"):
        strategy.sweep(vault.address, {"from": gov})

    # TODO: If you add protected tokens to the strategy.
    # Protected token doesn't work
    # with reverts("!protected"):
    #     strategy.sweep(strategy.protectedToken(), {"from": gov})

    before_balance = borrow_token.balanceOf(gov)
    borrow_token.transfer(
        strategy, 1 * (10 ** borrow_token.decimals()), {"from": borrow_whale}
    )
    assert borrow_token.address != strategy.want()
    strategy.sweep(borrow_token, {"from": gov})
    assert (
        borrow_token.balanceOf(gov)
        == 1 * (10 ** borrow_token.decimals()) + before_balance
    )


def test_triggers(gov, vault, strategy, token_whale, token):
    # Deposit to the vault and harvest
    token.approve(vault, 2 ** 256 - 1, {"from": token_whale})
    vault.deposit(500_000 * (10 ** token.decimals()), {"from": token_whale})
    vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})

    chain.sleep(1)
    strategy.harvest({"from": gov})

    strategy.harvestTrigger(0)
    strategy.tendTrigger(0)
