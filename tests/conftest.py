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
def keeper(accounts):
    yield accounts[5]


@pytest.fixture
def amount(accounts, token, user):
    amount = 10_000 * 10 ** token.decimals()
    # In order to get some funds for the token you are about to use,
    # it impersonate an exchange address to use it's funds.
    reserve = accounts.at("0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270", force=True)
    token.transfer(user, amount, {"from": reserve})
    yield amount


@pytest.fixture(scope="session")
def yvDAI():
    vault = Contract("0x9cfeb5e00a38ed1c9950dbadc0821ce4cb648a90")
    yield vault


@pytest.fixture(scope="session")
def wmatic():
    yield Contract("0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270")


@pytest.fixture(scope="session")
def dai():
    yield Contract("0x8f3cf7ad23cd3cadbd9735aff958023239c6a063")


@pytest.fixture(scope="session")
def vddai():
    yield interface.IVariableDebtToken("0x75c4d1fb84429023170086f06e682dcbbf537b7d")


@pytest.fixture(scope="session")
def amwmatic():
    yield interface.IAToken("0x8df3aad3a84da6b69a4da8aec3ea40d9091b2ac4")


@pytest.fixture(scope="session")
def wmatic_whale(accounts):
    yield accounts.at("0x2bb25175d9b0f8965780209eb558cc3b56ca6d32", force=True)


@pytest.fixture(scope="session")
def dai_whale(accounts):
    yield accounts.at("0x27f8d03b3a2196956ed754badc28d73be8830a6e", force=True)


@pytest.fixture(scope="session")
def token(wmatic):
    yield wmatic


@pytest.fixture
def dai_amount(user, dai):
    dai_amount = 10 ** dai.decimals()
    user.transfer(dai, dai_amount)
    yield dai_amount


@pytest.fixture(scope="function")
def vault(pm, gov, rewards, guardian, management, token):
    Vault = pm(config["dependencies"][0]).Vault
    vault = guardian.deploy(Vault)
    vault.initialize(token, gov, rewards, "", "", guardian, {"from": gov})
    vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
    vault.setManagement(management, {"from": gov})
    vault.setManagementFee(0, {"from": gov})
    vault.setPerformanceFee(0, {"from": gov})
    yield vault


@pytest.fixture(scope="function", autouse=True)
def vault_whale_withdraw(vault, wmatic_whale, dai, yvDAI, dai_whale):
    yield
    chain.sleep(10 * 3600 + 1)
    chain.mine(1)
    # more to compensate interests cost until withdrawal
    dai.transfer(yvDAI, Wei("50_000 ether"), {"from": dai_whale})
    # after test, withdraw
    if vault.balanceOf(wmatic_whale) > 0:
        vault.withdraw({"from": wmatic_whale})
        assert vault.balanceOf(wmatic_whale) == 0


@pytest.fixture(scope="function", autouse=True)
def initial_vault_balance(token, vault):
    yield token.balanceOf(vault.address)


@pytest.fixture(scope="function", autouse=True)
def initial_vault_assets(vault):
    yield vault.totalAssets()


@pytest.fixture(scope="function")
def strategy(strategist, vault, Strategy, gov, yvDAI):
    strategy = strategist.deploy(
        Strategy, vault, yvDAI, True, True, "StrategyLenderWMATICBorrowerDAI"
    )
    vault.addStrategy(strategy, 200, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    yield strategy


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5
