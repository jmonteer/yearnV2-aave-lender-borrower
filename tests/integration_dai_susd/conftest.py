import pytest
from brownie import config, chain, Wei
from brownie import Contract


@pytest.fixture(scope="session")
def yvDAI():
    yield Contract("0xdA816459F1AB5631232FE5e97a05BBBb94970c95")


@pytest.fixture(scope="session")
def yvSUSD():
    yield Contract("0xa5cA62D95D24A4a350983D5B8ac4EB8638887396")


@pytest.fixture(scope="session")
def vault():
    yield yvDAI


@pytest.fixture(scope="session")
def gov(accounts):
    vault = Contract("0xdA816459F1AB5631232FE5e97a05BBBb94970c95")
    yield accounts.at(vault.governance(), force=True)


@pytest.fixture(scope="session")
def dai():
    yield Contract("0x6B175474E89094C44Da98b954EedeAC495271d0F")


@pytest.fixture(scope="session")
def dai_whale():
    yield Contract("0xC3D03e4F041Fd4cD388c549Ee2A29a9E5075882f")


@pytest.fixture(scope="session")
def vdsusd():
    yield Contract("0xdC6a3Ab17299D9C2A412B0e0a4C1f55446AE0817")


@pytest.fixture(scope="session")
def susd():
    yield Contract("0x57Ab1ec28D129707052df4dF418D58a2D46d5f51")


@pytest.fixture(scope="session")
def susd_whale():
    yield Contract("0xA5407eAE9Ba41422680e2e00537571bcC53efBfD")


@pytest.fixture(scope="class")
def strategy(strategist, vault, Strategy, gov, yvDAI):
    strategy = strategist.deploy(
        Strategy, yvDAI, yvSUSD, True, True, "StrategyLenderDAIBorrowerSUSD"
    )
    vault.addStrategy(strategy, 200, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    yield strategy
