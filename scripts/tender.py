from brownie import Contract, accounts


def main():
    keeper = accounts[0]
    strat = Contract("0x2eF5D739E1052a5F18cBECb5C9E09254A8A11dB8")

    if strat.tendTrigger(1):
        strat.tend({"from": keeper})
