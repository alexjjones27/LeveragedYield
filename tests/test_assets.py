import pytest

from leveraged_yield.assets import family, is_plain_stable, native_symbol, normalize_symbol


@pytest.mark.parametrize("symbol,expected", [
    ("ETH", "WETH"), ("steth", "WSTETH"), ("eETH", "WEETH"), ("WSOL", "SOL"), ("USD₮0", "USDT0"),
    ("USDC", "USDC"),
])
def test_normalize(symbol, expected):
    assert normalize_symbol(symbol) == expected


@pytest.mark.parametrize("symbol,fam", [
    ("WETH", "ETH"), ("WSTETH", "ETH"), ("WEETH", "ETH"), ("RSETH", "ETH"), ("CBETH", "ETH"),
    ("WBTC", "BTC"), ("CBBTC", "BTC"), ("LBTC", "BTC"),
    ("USDC", "USD"), ("SUSDE", "USD"), ("SYRUPUSDC", "USD"), ("GHO", "USD"), ("DAI", "USD"),
    ("SOL", "SOL"), ("JITOSOL", "SOL"),
    ("EURC", "EUR"), ("ETHFI", "ETHFI"), ("LINK", "LINK"),
])
def test_family(symbol, fam):
    assert family(symbol) == fam


def test_plain_stables():
    assert is_plain_stable("USDC") and is_plain_stable("USDT")
    assert not is_plain_stable("SUSDE")


def test_native_gas_token_is_chain_specific():
    assert native_symbol("Ethereum") == "WETH"
    assert native_symbol("Base") == "WETH"
    assert native_symbol("BSC") == "WBNB"
    assert native_symbol("Berachain") == "WBERA"
    assert native_symbol("SomeNewChain").startswith("NATIVE-")
