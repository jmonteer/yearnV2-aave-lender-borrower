import pytest
from brownie import config, chain, Wei
from brownie import Contract


@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


@pytest.fixture(autouse=True)
def AaveLibrary(gov, AaveLenderBorrowerLib):
    yield AaveLenderBorrowerLib.deploy({"from": gov})


@pytest.fixture
def gov(accounts):
    yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)


@pytest.fixture
def user(accounts):
    yield accounts[0]


@pytest.fixture
def rewards(accounts):
    yield accounts[1]


@pytest.fixture
def guardian(accounts):
    yield accounts[2]


@pytest.fixture
def management(accounts):
    yield accounts[3]


@pytest.fixture
def strategist(accounts):
    yield accounts[4]


@pytest.fixture
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


@pytest.fixture
def weth():
    yield Contract("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")


@pytest.fixture
def vdweth():
    yield Contract("0xF63B34710400CAd3e044cFfDcAb00a0f32E33eCf")


@pytest.fixture
def wbtc():
    yield Contract("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599")


@pytest.fixture
def lendingPool():
    yield Contract("0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9")


@pytest.fixture
def aToken(token, lendingPool):
    yield Contract(lendingPool.getReserveData(token).dict()["aTokenAddress"])


@pytest.fixture
def vdToken(borrow_token, lendingPool):
    yield Contract(
        lendingPool.getReserveData(borrow_token).dict()["variableDebtTokenAddress"]
    )


@pytest.fixture
def awbtc():
    yield Contract("0x9ff58f4fFB29fA2266Ab25e75e2A8b3503311656")


@pytest.fixture
def wbtc_whale(accounts):
    yield accounts.at("0x40ec5B33f54e0E8A33A975908C5BA1c14e5BbbDf", force=True)


@pytest.fixture
def weth_whale(accounts):
    yield accounts.at("0x2F0b23f53734252Bda2277357e97e1517d6B042A", force=True)


addresses = {
    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",  # WBTC
    "YFI": "0x0bc529c00C6401aEF6D220BE8C6Ea1667F6Ad93e",  # YFI
    "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
    "LINK": "0x514910771AF9Ca656af840dff83E8264EcF986CA",  # LINK
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
    "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",  # DAI
    "USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
}


@pytest.fixture(
    params=[
        # 'WBTC', # WBTC
        # "YFI",  # YFI
        # "WETH",  # WETH
        # 'LINK', # LINK
        # 'USDT', # USDT
        "DAI"
    ]
)
def token(request):
    yield Contract(addresses[request.param])


@pytest.fixture(
    params=[
        # "yvWBTC", # yvWBTC
        # "yvWETH", # yvWETH
        # "yvUSDT",  # yvUSDT
        # "yvUSDC", # yvUSDC
        # "yvDAI" # yvDAI
        "yvSUSD"
    ],
)
def yvault(request):
    addresses = {
        "yvWBTC": "0xA696a63cc78DfFa1a63E9E50587C197387FF6C7E",  # yvWBTC
        "yvWETH": "0xa258C4606Ca8206D8aA700cE2143D7db854D168c",  # yvWETH
        "yvUSDT": "0x7Da96a3891Add058AdA2E826306D812C638D87a7",  # yvUSDT
        "yvUSDC": "0x5f18C75AbDAe578b483E5F43f12a39cF75b973a9",  # yvUSDC
        "yvDAI": "0x19D3364A399d251E894aC732651be8B0E4e85001",  # yvDAI
        "yvSUSD": "0xa5cA62D95D24A4a350983D5B8ac4EB8638887396",
    }
    vault = Contract(addresses[request.param])
    vault.setDepositLimit(
        2 ** 256 - 1, {"from": vault.governance()}
    )  # testing during war room
    yield vault


@pytest.fixture
def borrow_token(yvault):
    yield Contract(yvault.token())


whales = {
    "WBTC": "0x28c6c06298d514db089934071355e5743bf21d60",  # binance14
    "WETH": "0x28c6c06298d514db089934071355e5743bf21d60",
    "LINK": "0x28c6c06298d514db089934071355e5743bf21d60",
    "YFI": "0x28c6c06298d514db089934071355e5743bf21d60",
    "USDT": "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503",  #
    "USDC": "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503",
    "DAI": "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503",  #
    "sUSD": "0xA5407eAE9Ba41422680e2e00537571bcC53efBfD",
}


@pytest.fixture
def borrow_whale(borrow_token):
    yield whales[borrow_token.symbol()]


@pytest.fixture
def token_whale(token):
    yield whales[token.symbol()]


@pytest.fixture
def token_symbol(token):
    yield token.symbol()


@pytest.fixture
def weth_amout(user, weth):
    weth_amout = 10 ** weth.decimals()
    user.transfer(weth, weth_amout)
    yield weth_amout


@pytest.fixture
def registry():
    yield Contract("0x50c1a2eA0a861A967D9d0FFE2AE4012c2E053804")


@pytest.fixture
def live_vault(registry, token):
    yield registry.latestVault(token)


@pytest.fixture
def vault(pm, gov, rewards, guardian, management, token):
    Vault = pm(config["dependencies"][0]).Vault
    vault = guardian.deploy(Vault)
    vault.initialize(token, gov, rewards, "", "", guardian, management, {"from": gov})

    vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
    vault.setManagementFee(0, {"from": gov})
    vault.setPerformanceFee(0, {"from": gov})
    yield vault


incentivised = {
    "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599": True,  # WBTC
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": True,  # WETH
    "0x0bc529c00C6401aEF6D220BE8C6Ea1667F6Ad93e": False,  # YFI
    "0x514910771AF9Ca656af840dff83E8264EcF986CA": False,  # LINK
    "0x6B175474E89094C44Da98b954EedeAC495271d0F": True,  # DAI
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": True,  # USDC
    "0xdAC17F958D2ee523a2206206994597C13D831ec7": True,  # USDT
    "0x57Ab1ec28D129707052df4dF418D58a2D46d5f51": True,  # SUSD
}


@pytest.fixture
def token_incentivised(token):
    yield incentivised[token.address]


@pytest.fixture
def borrow_incentivised(borrow_token):
    yield incentivised[borrow_token.address]


@pytest.fixture
def strategy(vault, Strategy, gov, cloner):
    strategy = Strategy.at(cloner.original())
    vault.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 0, {"from": gov})
    chain.mine()
    yield strategy


@pytest.fixture
def RELATIVE_APPROX():
    yield 1e-5


@pytest.fixture
def cloner(
    strategist,
    vault,
    AaveLenderBorrowerCloner,
    yvault,
    token_incentivised,
    borrow_incentivised,
    token,
    borrow_token,
):
    cloner = strategist.deploy(
        AaveLenderBorrowerCloner,
        vault,
        yvault,
        token_incentivised,
        borrow_incentivised,
        f"Strategy{token.symbol()}Lender{borrow_token.symbol()}Borrower",
    )

    yield cloner
