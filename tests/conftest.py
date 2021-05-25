import pytest
from brownie import config, chain, Wei
from brownie import Contract


@pytest.fixture(autouse=True)
def clean():
    chain.snapshot()
    yield
    chain.revert()


@pytest.fixture(scope="session")
def gov(accounts):
    yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)


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
    reserve = accounts.at("0xd551234ae421e3bcba99a0da6d736074f22192ff", force=True)
    token.transfer(user, amount, {"from": reserve})
    yield amount


@pytest.fixture(scope="session")
def yvETH():
    vault = Contract("0xa9fE4601811213c340e850ea305481afF02f5b28")
    vault.setDepositLimit(
        2 ** 256 - 1, {"from": vault.governance()}
    )  # testing during war room
    yield vault


@pytest.fixture(scope="session")
def weth():
    yield Contract("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")


@pytest.fixture(scope="session")
def vdweth():
    yield Contract("0xF63B34710400CAd3e044cFfDcAb00a0f32E33eCf")


@pytest.fixture(scope="session")
def wbtc():
    yield Contract("0x2260fac5e5542a773aa44fbcfedf7c193bc2c599")


@pytest.fixture(scope="session")
def awbtc():
    yield Contract("0x9ff58f4fFB29fA2266Ab25e75e2A8b3503311656")


@pytest.fixture(scope="session")
def wbtc_whale(accounts):
    yield accounts.at("0x40ec5B33f54e0E8A33A975908C5BA1c14e5BbbDf", force=True)


@pytest.fixture(scope="session")
def weth_whale(accounts):
    yield accounts.at("0x2F0b23f53734252Bda2277357e97e1517d6B042A", force=True)


@pytest.fixture(scope="session")
def token(wbtc):
    yield wbtc


@pytest.fixture
def weth_amout(user, weth):
    weth_amout = 10 ** weth.decimals()
    user.transfer(weth, weth_amout)
    yield weth_amout


@pytest.fixture(scope="class")
def vault(pm, gov, rewards, guardian, management, token):
    Vault = pm(config["dependencies"][0]).Vault
    vault = guardian.deploy(Vault)
    vault.initialize(token, gov, rewards, management, "", "", guardian, {"from": gov})

    vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
    vault.setManagementFee(0, {"from": gov})
    vault.setPerformanceFee(0, {"from": gov})
    yield vault


@pytest.fixture(scope="function")
def vault_whale_deposit(vault, wbtc, wbtc_whale):
    print("Vault total assets:", vault.totalAssets() / (10 ** wbtc.decimals()))
    deposit_amount = 10 * 1e8
    assert vault.totalAssets() == 0
    wbtc.approve(vault, 2 ** 256 - 1, {"from": wbtc_whale})
    vault.deposit(deposit_amount, {"from": wbtc_whale})
    assert wbtc.balanceOf(vault) == deposit_amount
    print("Vault total assets:", vault.totalAssets() / (10 ** wbtc.decimals()))

    yield

    # after test, withdraw
    if vault.balanceOf(wbtc_whale) > 0:
        print("Withdrawing 100% from vault")
        vault.withdraw({"from": wbtc_whale})
        assert vault.totalAssets() == 0

    print("Vault total assets:", vault.totalAssets() / (10 ** wbtc.decimals()))


@pytest.fixture(scope="function", autouse=True)
def vault_whale_withdraw(vault, wbtc, wbtc_whale, weth, yvETH, weth_whale):
    yield
    chain.sleep(10 * 3600 + 1)
    chain.mine(1)
    # more to compensate interests cost until withdrawal
    weth.transfer(yvETH, Wei("500 ether"), {"from": weth_whale})
    # after test, withdraw
    if vault.balanceOf(wbtc_whale) > 0:
        print("Withdrawing 100% from vault")
        vault.withdraw({"from": wbtc_whale})
        assert vault.totalAssets() == 0


@pytest.fixture(scope="class")
def strategy(strategist, keeper, vault, Strategy, gov, yvETH):
    strategy = strategist.deploy(
        Strategy, vault, yvETH, True, True, "StrategyLenderWBTCBorrowerWETH"
    )
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})

    yield strategy


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5
