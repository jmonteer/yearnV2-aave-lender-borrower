import pytest

from brownie import config, chain, interface, Wei
from brownie import Contract


@pytest.fixture(autouse=True)
def clean():
    chain.snapshot()
    yield
    chain.revert()


@pytest.fixture(scope="session")
def gov(accounts):
    vault = Contract("0xCcba0B868106d55704cb7ff19782C829dc949feB")
    yield accounts.at(vault.governance(), force=True)


@pytest.fixture(scope="session")
def yvDAI():
    vault = Contract("0x9cfeb5e00a38ed1c9950dbadc0821ce4cb648a90")
    yield vault


@pytest.fixture(scope="class")
def vault(gov):
    yield Contract("0xCcba0B868106d55704cb7ff19782C829dc949feB", owner=gov)


@pytest.fixture(scope="class")
def strategy(strategist, vault, Strategy, gov, yvDAI):
    strategy = strategist.deploy(
        Strategy, vault, yvDAI, True, True, "StrategyLenderWMATICBorrowerDAI"
    )
    vault.addStrategy(strategy, 200, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    yield strategy


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5
