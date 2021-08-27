from brownie import chain, reverts, Contract


def test_set_swap_router_acl(strategy, gov, strategist, management, guardian, user):
    router = Contract("0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")

    strategy.setSwapRouter(router, {"from": gov})
    assert strategy.router() == router

    with reverts("!authorized"):
        strategy.setSwapRouter(router, {"from": strategist})

    with reverts("!authorized"):
        strategy.setSwapRouter(router, {"from": management})

    with reverts("!authorized"):
        strategy.setSwapRouter(router, {"from": guardian})

    with reverts("!authorized"):
        strategy.setSwapRouter(router, {"from": user})
