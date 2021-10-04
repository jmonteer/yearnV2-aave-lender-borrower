import pytest
from brownie import Contract, ZERO_ADDRESS


@pytest.fixture(scope="session")
def yvWETH():
    yield Contract("0xa258C4606Ca8206D8aA700cE2143D7db854D168c")


@pytest.fixture(scope="session")
def yvSUSD():
    yield Contract("0xa5cA62D95D24A4a350983D5B8ac4EB8638887396")


@pytest.fixture(scope="session")
def vault():
    yield yvWETH


@pytest.fixture(scope="session")
def gov(accounts):
    vault = Contract("0xdA816459F1AB5631232FE5e97a05BBBb94970c95")
    yield accounts.at(vault.governance(), force=True)


@pytest.fixture(scope="session")
def weth():
    yield Contract("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")


@pytest.fixture(scope="session")
def weth_whale():
    yield Contract("0x2F0b23f53734252Bda2277357e97e1517d6B042A")


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


@pytest.fixture(scope="function", autouse=True)
def vault_whale_withdraw(
    vault, token_whale, borrow_token, yvault, borrow_whale, vdToken, strategy
):
    # Override this method to replace the base conftest logic
    pass


@pytest.fixture(scope="class")
def strategy(strategist, yvWETH, Strategy, gov, yvSUSD):
    strategy = strategist.deploy(
        Strategy, yvWETH, yvSUSD, "StrategyLenderDAIBorrowerSUSD"
    )
    strategy.setStrategyParams(
        6_000,  # targetLTVMultiplier
        8_000,  # warningLTVMultiplier)
        0.05 * 1e27,  # acceptableCostsRay
        7,  # yearn aave referral code,
        2 ** 256 - 1,  #  _maxTotalBorrowIT,
        True,  # _isWantIncentivised -> DAI deposits with stkAAVE rewards
        True,  # _isInvestmentTokenIncentivised,
        False,  # _leaveDebtBehind,
        1,  # _maxLoss
        60 * 1e9,  # _maxGasPriceToTend
    )

    # reset debt ratio of all strategies
    for i in range(20):
        queued_strat = yvWETH.withdrawalQueue(i)
        if queued_strat == ZERO_ADDRESS:
            break
        yvWETH.updateStrategyDebtRatio(queued_strat, 0, {"from": gov})

    yvWETH.addStrategy(strategy, 10_000, 0, 2 ** 256 - 1, 1_000, {"from": gov})
    yield strategy
