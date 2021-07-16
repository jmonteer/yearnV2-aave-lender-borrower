from brownie import Wei


def test_direct_transfer_increments_estimated_total_assets(
    strategy,
    token,
    token_whale,
):
    initial = strategy.estimatedTotalAssets()
    amount = Wei("10 ether")
    token.transfer(strategy, amount, {"from": token_whale})
    assert strategy.estimatedTotalAssets() == initial + amount


def test_direct_transfer_increments_profits(vault, strategy, token, token_whale, gov):
    initialProfit = vault.strategies(strategy).dict()["totalGain"]
    assert initialProfit == 0

    amount = Wei("10 ether")
    token.transfer(strategy, amount, {"from": token_whale})
    strategy.harvest({"from": gov})
    assert vault.strategies(strategy).dict()["totalGain"] == initialProfit + amount
