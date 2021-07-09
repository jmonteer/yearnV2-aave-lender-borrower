from brownie import Contract, accounts

def main():
    keeper = accounts[0]
    strategyLenderWethBorrowerDAI = Contract("0x2eF5D739E1052a5F18cBECb5C9E09254A8A11dB8")
    ssc_dai_am3crv = Contract("0x69eC103528B3D8F657a563c4BcCc5025678BB103")
    curveam3CRV = Contract("0xab8f0128ecbF90aA73A0C5a79E549A194f4C2354")
    
    curveam3CRV.harvest({"from": keeper})
    ssc_dai_am3crv.harvest({"from: keeper"})
    strategyLenderWethBorrowerDAI.harvest({"from": keeper})

