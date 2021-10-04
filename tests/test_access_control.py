from brownie import chain, reverts, Contract


def test_switch_dex_acl(strategy, gov, strategist, management, guardian, user):
    uniswap = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
    sushiswap = "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F"

    with reverts("!authorized"):
        strategy.switchDex(True, {"from": user})

    with reverts("!authorized"):
        strategy.switchDex(True, {"from": guardian})

    with reverts("!authorized"):
        strategy.switchDex(True, {"from": strategist})

    strategy.switchDex(True, {"from": management})
    assert strategy.router() == uniswap

    strategy.switchDex(False, {"from": management})
    assert strategy.router() == sushiswap

    strategy.switchDex(True, {"from": gov})
    assert strategy.router() == uniswap

    strategy.switchDex(False, {"from": gov})
    assert strategy.router() == sushiswap
