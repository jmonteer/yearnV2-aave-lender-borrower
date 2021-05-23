import pytest
from brownie import config, chain, Wei
from brownie import Contract


@pytest.fixture(scope="session")
def gov(accounts):
    yield accounts.at("0x16388463d60FFE0661Cf7F1f31a7D658aC790ff7", force=True)


@pytest.fixture(scope="session")
def user(accounts):
    yield accounts[0]


@pytest.fixture(scope="session")
def rewards(accounts):
    yield accounts[1]


@pytest.fixture(scope="session")
def guardian(accounts):
    yield accounts[2]


@pytest.fixture(scope="session")
def management(accounts):
    yield accounts[3]


@pytest.fixture(scope="session")
def strategist(accounts):
    yield accounts[4]


@pytest.fixture(scope="session")
def yvUSDC():
    yield Contract("0x71955515ADF20cBDC699B8bC556Fc7Fd726B31B0")


@pytest.fixture(scope="session")
def link():
    yield Contract("0x514910771af9ca656af840dff83e8264ecf986ca")


@pytest.fixture(scope="session")
def usdc():
    yield Contract("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")


@pytest.fixture(scope="session")
def link_whale(accounts):
    yield accounts.at("0xbe6977e08d4479c0a6777539ae0e8fa27be4e9d6", force=True)


@pytest.fixture(scope="session")
def usdc_whale(accounts):
    yield accounts.at("0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503", force=True)


@pytest.fixture(scope="session")
def token(link):
    yield link


@pytest.fixture(scope="class")
def vault(gov):
    yield Contract("0xf962b098ecc4352aa2ad1d4164bd2b8367fd94c3", owner=gov)


@pytest.fixture(scope="class")
def strategy(strategist, vault, Strategy, yvUSDC):
    strategy = strategist.deploy(
        Strategy, vault, yvUSDC, False, True, "StrategyLenderLINKBorrowerUSDC"
    )

    vault.revokeStrategy("0x3aD22Fd9e2cc898d6F77AC12eAc603A77a464c45")
    vault.revokeStrategy("0xA875a88dc765BA2B598F858b1D95111D519fd43E")
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 1_000)
    strategy.setStrategyParams(
        6_000,  # _targetLTVMultiplier
        7_000,  # _warningLTVMultiplier
        8 * 1e27,  # _acceptableCostsRay
        0,  # _aaveReferral
        2 ** 256 - 1,  # _maxTotalBorrowIT
        False,  # _isWantIncentivised
        True,  # _isInvestmentTokenIncentivised
        False,  # leaveDebtBehind
        1,  # maxLoss
        {"from": strategist},
    )

    yield strategy
