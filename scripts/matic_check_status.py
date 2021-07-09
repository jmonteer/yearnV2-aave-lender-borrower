from brownie import Contract


def main():
    strat = Contract("0x2eF5D739E1052a5F18cBECb5C9E09254A8A11dB8")
    dai = Contract("0x8f3cf7ad23cd3cadbd9735aff958023239c6a063")
    pd_provider = Contract("0x7551b5D2763519d4e37e8B81929D336De671d46d")
    a_provider = Contract(pd_provider.ADDRESSES_PROVIDER())
    lp = Contract(a_provider.getLendingPool())

    data = lp.getUserAccountData(strat).dict()
    total_collateral = data["totalCollateralETH"]
    total_debt = data["totalDebtETH"]
    print(f"LTV: {total_debt/total_collateral*100.0}")

    reserve_data = lp.getReserveData(dai).dict()
    print(f"Borrow rate: {reserve_data['currentVariableBorrowRate']/1e27*100.0}")
