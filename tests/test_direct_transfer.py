from brownie import Wei


def test_direct_transfer_increments_estimated_total_assets(
    strategy,
    wmatic,
    wmatic_whale,
):
    initial = strategy.estimatedTotalAssets()
    amount = Wei("100 ether")
    wmatic.transfer(strategy, amount, {"from": wmatic_whale})
    assert strategy.estimatedTotalAssets() == initial + amount


def test_direct_transfer_increments_profits(
    vault,
    strategy,
    wmatic,
    wmatic_whale
):
    initialProfit = vault.strategies(strategy).dict()["totalGain"]
    assert initialProfit == 0

    amount = Wei("100 ether")
    wmatic.transfer(strategy, amount, {"from": wmatic_whale})
    strategy.harvest()
    assert vault.strategies(strategy).dict()["totalGain"] == initialProfit + amount


def test_deposit_should_not_increment_profits(
    vault,
    strategy,
    wmatic,
    wmatic_whale
):
    initialProfit = vault.strategies(strategy).dict()["totalGain"]
    assert initialProfit == 0

    wmatic.approve(vault, 2 ** 256 - 1, {"from": wmatic_whale})
    vault.deposit(Wei("100 ether"), {"from": wmatic_whale})
    strategy.harvest()
    assert vault.strategies(strategy).dict()["totalGain"] == initialProfit

