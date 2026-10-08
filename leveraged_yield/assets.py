"""Token symbol normalisation and price-family classification."""

from __future__ import annotations

import re

NATIVE_EVM = "0x0000000000000000000000000000000000000000"
NATIVE_SOL = "so11111111111111111111111111111111111111112"

# Wrapped native gas token for chains whose gas token is not ETH. Every other
# EVM chain DefiLlama lists with a 0x000.. underlying is treated as ETH-native.
NON_ETH_NATIVE = {
    "BSC": "WBNB", "Polygon": "WPOL", "Avalanche": "WAVAX", "Berachain": "WBERA",
    "Sonic": "WS", "Gnosis": "WXDAI", "Mantle": "WMNT", "Hyperliquid L1": "WHYPE",
    "Monad": "WMON", "Plasma": "WXPL", "Celo": "CELO", "Metis": "METIS", "Kava": "WKAVA",
    "Fantom": "WFTM", "Cronos": "WCRO", "Moonbeam": "WGLMR", "Core": "WCORE", "Flow": "WFLOW",
    "Sei": "WSEI", "Rootstock": "WRBTC", "Bitlayer": "WBTC", "Merlin": "WBTC", "Klaytn": "WKLAY",
    "Kaia": "WKAIA", "Ronin": "WRON", "Harmony": "WONE", "Aurora": "WETH", "Tron": "TRX",
    "Stacks": "STX", "Sui": "SUI", "Aptos": "APT", "Near": "NEAR", "TON": "TON",
}
ETH_NATIVE_CHAINS = {
    "Ethereum", "Arbitrum", "Base", "OP Mainnet", "Linea", "Scroll", "zkSync Era", "Blast",
    "Mode", "Unichain", "Ink", "Soneium", "World Chain", "Taiko", "Manta", "MegaETH", "Lisk",
    "Abstract", "Zora", "Starknet", "Katana", "Swellchain", "Fraxtal", "Boba", "Morph",
    "Polygon zkEVM", "Arbitrum Nova", "Hemi",
}


def native_symbol(chain: str) -> str:
    """Symbol for a chain's native gas token (DefiLlama's 0x000.. underlying)."""
    if chain in NON_ETH_NATIVE:
        return NON_ETH_NATIVE[chain]
    if chain in ETH_NATIVE_CHAINS:
        return "WETH"
    return f"NATIVE-{chain.upper()}"


# Symbols that represent the same economic token for our purposes.
ALIASES = {
    "ETH": "WETH",
    "STETH": "WSTETH",
    "EETH": "WEETH",
    "WSOL": "SOL",
    "USD₮0": "USDT0",
    "USD₮": "USDT",
}

ETH_FAMILY = {
    "WETH", "WSTETH", "WEETH", "RETH", "CBETH", "OSETH", "RSETH", "EZETH", "METH",
    "CMETH", "ETHX", "SFRXETH", "FRXETH", "SWETH", "LSETH", "ANKRETH", "OETH", "WOETH",
    "TETH", "PUFETH", "WBETH", "UNIETH", "PZETH", "WRSETH", "AGETH", "UETH", "GETH",
}
SOL_FAMILY = {"SOL", "JITOSOL", "MSOL", "JUPSOL", "BSOL", "BBSOL", "INF", "HSOL", "DSOL",
              "VSOL", "STSOL", "BNSOL", "DFDVSOL", "PICOSOL", "HUBSOL", "LAINESOL", "CGNTSOL"}
USD_NAMED = {"DAI", "SDAI", "GHO", "SGHO", "FRAX", "SFRAX", "LUSD", "BOLD", "SBOLD", "DOLA",
             "SDOLA", "AUSD", "USDE", "SUSDE", "EUSDE", "PYUSD", "RLUSD", "USDS", "SUSDS",
             "USDTB", "MIM", "TUSD", "FDUSD", "USD0", "USD0++", "BUIDL", "USTB", "USYC"}
PLAIN_STABLES = {"USDC", "USDT", "USDT0", "DAI", "USDS", "PYUSD", "RLUSD", "FDUSD", "TUSD",
                 "USDC.E", "USDBC", "GHO", "LUSD", "FRAX", "FRXUSD", "USDG", "USD1", "AUSD",
                 "USDTB", "BOLD", "DOLA", "CRVUSD", "EURC", "EURE"}
NOT_ETH = {"ETHFI", "ETHENA", "SETH2"}


def normalize_symbol(symbol: str | None) -> str:
    if not symbol:
        return ""
    s = symbol.strip().upper().replace("₮", "T")
    return ALIASES.get(s, s)


def family(symbol: str) -> str:
    """Return the price family a token tracks: USD, ETH, BTC, SOL, EUR or itself."""
    s = normalize_symbol(symbol)
    if s in ETH_FAMILY:
        return "ETH"
    if s in SOL_FAMILY:
        return "SOL"
    if "BTC" in s:
        return "BTC"
    if "EUR" in s:
        return "EUR"
    if s in USD_NAMED or "USD" in s:
        return "USD"
    if s not in NOT_ETH and re.fullmatch(r"[A-Z]*ETH", s):
        return "ETH"
    if re.fullmatch(r"[A-Z]+SOL", s):
        return "SOL"
    return s


def is_plain_stable(symbol: str) -> bool:
    return normalize_symbol(symbol) in PLAIN_STABLES


def same_family(a: str, b: str) -> bool:
    return family(a) == family(b)
