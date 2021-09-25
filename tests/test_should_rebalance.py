def test_all_params_in_range_should_not_rebalance(AaveLibrary, borrow_token):
    assert (
        AaveLibrary.shouldRebalance(
            borrow_token,
            1e27,  # acceptable costs
            5_000,  # target LTV
            6_000,  # warning LTV
            1_000,  # total collateral ETH
            500,  # total debt ETH
            600 * 1e9  # max gas price to tend
            # test lib enforcing 100 gwei current gas price
        )
        == False
    )


def test_current_ltv_higher_than_warning_should_adjust(AaveLibrary, borrow_token):
    assert (
        AaveLibrary.shouldRebalance(
            borrow_token,
            1e27,  # acceptable costs
            5_000,  # target LTV
            6_000,  # warning LTV
            1_000,  # total collateral ETH
            601,  # total debt ETH
            600 * 1e9  # max gas price to tend
            # test lib enforcing 100 gwei current gas price
        )
        == True
    )


def test_current_ltv_higher_than_warning_should_adjust_even_with_expensive_gas(
    AaveLibrary, borrow_token
):
    assert (
        AaveLibrary.shouldRebalance(
            borrow_token,
            1e27,  # acceptable costs
            5_000,  # target LTV
            4_999,  # warning LTV
            1_000,  # total collateral ETH
            500,  # total debt ETH
            0  # max gas price set to 0 gwei here to make sure we rebalance even if higher than max price
            # test lib enforcing 100 gwei current gas price
        )
        == True
    )


def test_high_borrow_cost_with_lower_gas_should_adjust(AaveLibrary, borrow_token):
    assert (
        AaveLibrary.shouldRebalance(
            borrow_token,
            0.0001 * 1e27,  # 0.01% max acceptable cost
            5_000,  # target LTV
            6_000,  # warning LTV
            1_000,  # total collateral ETH
            500,  # total debt ETH
            101 * 1e9  # 6000 gwei max price to make sure we are under it
            # test lib enforcing 100 gwei current gas price
        )
        == True
    )


def test_high_borrow_cost_with_expensive_gas_should_not_adjust(
    AaveLibrary, borrow_token
):
    assert (
        AaveLibrary.shouldRebalance(
            borrow_token,
            0.0001 * 1e27,  # 0.01% max acceptable cost
            5_000,  # target LTV
            6_000,  # warning LTV
            1_000,  # total collateral ETH
            500,  # total debt ETH
            99 * 1e9  # 1 gwei max price to make sure we are over it
            # test lib enforcing 100 gwei current gas price
        )
        == False
    )


def test_take_more_debt_with_cheap_gas_should_adjust(AaveLibrary, borrow_token):
    # current ltv = debt / colateral - 39 so it does adjust (over 10 bps to the other side)
    assert (
        AaveLibrary.shouldRebalance(
            borrow_token,
            1e27,  # acceptable costs
            5_000,  # target LTV
            6_000,  # warning LTV
            1_000,  # total collateral ETH
            390,  # total debt ETH
            600 * 1e9  # max gas price to tend - 600 gwei
            # test lib enforcing 100 gwei current gas price
        )
        == True
    )


def test_take_more_debt_with_expensive_gas_should_not_adjust(AaveLibrary, borrow_token):
    # current ltv = debt / colateral - 39 so it does adjust (over 10 bps to the other side)
    assert (
        AaveLibrary.shouldRebalance(
            borrow_token,
            1e27,  # acceptable costs
            5_000,  # target LTV
            6_000,  # warning LTV
            1_000,  # total collateral ETH
            390,  # total debt ETH
            99 * 1e9  # max gas price to tend - 99 gwei
            # test lib enforcing 100 gwei current gas price
        )
        == False
    )


def test_take_more_debt_under_rebalancing_band_should_not_adjust(
    AaveLibrary, borrow_token
):
    # current ltv = debt / colateral - 41 so it does not adjust (less than 10 bps to the other side)
    assert (
        AaveLibrary.shouldRebalance(
            borrow_token,
            1e27,  # acceptable costs
            5_000,  # target LTV
            6_000,  # warning LTV
            1_000,  # total collateral ETH
            410,  # total debt ETH
            600 * 1e9  # max gas price to tend - 600 gwei
            # test lib enforcing 100 gwei current gas price
        )
        == False
    )
