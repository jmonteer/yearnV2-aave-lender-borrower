import brownie
from brownie import Contract, Wei
import pytest


def test_operation(
    token, vault, wmatic_whale, strategy, RELATIVE_APPROX
):
    user_balance_before = token.balanceOf(wmatic_whale)

    token.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10 ether"), {"from": wmatic_whale})
    amount = Wei("10 ether")
    # Deposit to the vault
    assert token.balanceOf(vault.address) == amount

    # harvest
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # tend()
    strategy.tend()

    # withdrawal
    vault.withdraw({"from": wmatic_whale})
    assert (
        pytest.approx(token.balanceOf(wmatic_whale), rel=RELATIVE_APPROX)
        == user_balance_before
    )


def test_emergency_exit(
    token, vault, strategy, wmatic_whale, RELATIVE_APPROX
):
    # Deposit to the vault
    token.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10 ether"), {"from": wmatic_whale})
    amount = Wei("10 ether")
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # set emergency and exit
    strategy.setEmergencyExit()
    strategy.harvest()
    assert strategy.estimatedTotalAssets() < amount


def test_profitable_harvest(
    token,
    vault,
    strategy,
    wmatic_whale,
    RELATIVE_APPROX,
    chain,
    dai,
    dai_whale,
    yvDAI,
):
    # Deposit to the vault
    token.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10 ether"), {"from": wmatic_whale})
    amount = Wei("10 ether")
    assert token.balanceOf(vault.address) == amount

    # Harvest 1: Send funds through the strategy
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # increase rewards, lending interest and borrowing interests
    chain.sleep(50 * 24 * 3600)
    chain.mine(1)

    strategy.harvest()  # to claim and start cooldown

    chain.sleep(10 * 24 * 3600 + 1)  # sleep during cooldown
    chain.mine(1)

    dai.transfer(yvDAI, Wei("20_000 ether"), {"from": dai_whale})
    before_pps = vault.pricePerShare()
    # Harvest 2: Realize profit
    strategy.harvest()
    chain.sleep(3600 * 6)  # 6 hrs needed for profits to unlock
    chain.mine(1)
    profit = token.balanceOf(vault.address)  # Profits go to vault

    assert vault.totalAssets() > amount
    assert vault.pricePerShare() > before_pps


def test_change_debt(
    gov, token, vault, wmatic_whale, strategy, user, strategist, RELATIVE_APPROX
):
    # Deposit to the vault and harvest
    token.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10 ether"), {"from": wmatic_whale})
    vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})
    strategy.harvest()
    amount = Wei("10 ether")
    half = int(amount / 2)

    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == half

    vault.updateStrategyDebtRatio(strategy.address, 10_000, {"from": gov})
    strategy.harvest()
    assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == amount

    # In order to pass this tests, you will need to implement prepareReturn.
    # TODO: uncomment the following lines.
    # vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})
    # strategy.harvest()
    # assert pytest.approx(strategy.estimatedTotalAssets(), rel=RELATIVE_APPROX) == half


def test_sweep(gov, vault, strategy, token, wmatic_whale, user, dai_whale, dai):
    # Strategy want token doesn't work
    token.transfer(strategy, 10e8, {"from": wmatic_whale})
    assert token.address == strategy.want()
    assert token.balanceOf(strategy) > 0
    with brownie.reverts("!want"):
        strategy.sweep(token, {"from": gov})

    # Vault share token doesn't work
    with brownie.reverts("!shares"):
        strategy.sweep(vault.address, {"from": gov})

    # TODO: If you add protected tokens to the strategy.
    # Protected token doesn't work
    # with brownie.reverts("!protected"):
    #     strategy.sweep(strategy.protectedToken(), {"from": gov})

    before_balance = dai.balanceOf(gov)
    dai.transfer(strategy, Wei("1 ether"), {"from": dai_whale})
    assert dai.address != strategy.want()
    strategy.sweep(dai, {"from": gov})
    assert dai.balanceOf(gov) == Wei("1 ether") + before_balance


def test_triggers(gov, vault, strategy, wmatic_whale, token, user, dai, strategist):
    # Deposit to the vault and harvest
    token.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("10 ether"), {"from": wmatic_whale})
    vault.updateStrategyDebtRatio(strategy.address, 5_000, {"from": gov})
    strategy.harvest()

    strategy.harvestTrigger(0)
    strategy.tendTrigger(0)
