import requests
import json
import logging
import time
import os
import sys
from dotenv import load_dotenv
from util import get_fleek_client

load_dotenv()

SWAP_STATS_FILE_PATH = os.environ["SWAP_STATS_FILE_PATH"]
FLEEK_KEY_ID = os.environ["FLEEK_KEY_ID"]
FLEEK_KEY = os.environ["FLEEK_KEY"]
FLEEK_BUCKET = os.environ["FLEEK_BUCKET"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

stableSwapAddress = "0x3911f80530595fbd01ab1516ab61255d75aeb066"
btcSwapAddress = "0x4f6a43ad7cba042606decaca730d4ce0a57ac62e"
vETH2SwapAddress = "0xdec2157831d6abc3ec328291119cc91b337272b5"

# coingecko api accepts case insensitive but returns lowercase addresses
VETH2TokenAddress = "0x898BAD2774EB97cF6b94605677F43b41871410B1".lower()
WETHTokenAddress = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2".lower()
USDv2LPTokenAddress  = "0x5f86558387293b6009d7896A61fcc86C17808D62".lower()

payload = {}
EMPTY_PAYLOAD_ITEM = {
    "oneDayVolume": 0,
    "APY": 0,
    "TVL": 0,
}


def get_token_prices_usd(tokenAddresses):
    tokenPricesUSD = dict()

    try:
        url = ("https://api.coingecko.com/api/v3/simple/token_price"
               "/ethereum?contract_addresses={}"
               "&vs_currencies=usd""".format(','.join(tokenAddresses)))
        r = requests.get(url)
    except Exception as e:
        logger.error(f"Error getting price data from coinGecko: {e}")
        return

    for tokenAddress, price in r.json().items():
        if price == {}:
            logger.error("Error getting price data for token: {}".format(
                tokenAddress
            ))
        else:
            tokenPricesUSD[tokenAddress] = float(price["usd"])
    # hardcode 1 USD as the price for USDv2 LP tokens
    tokenPricesUSD[USDv2LPTokenAddress] = 1
    # use WETH price for VETH2
    if WETHTokenAddress in tokenPricesUSD:
        tokenPricesUSD[VETH2TokenAddress] = tokenPricesUSD[WETHTokenAddress]
        return tokenPricesUSD
    else:
        return


def get_graph_data():
    graphURL = "https://api.thegraph.com/subgraphs/name/saddle-finance/saddle"
    yesterday = int(time.time()) - 3600*24
    swapsDailyVolumeGraphQuery = """{{
        swaps {{
            id
            balances
            tokens {{
              id
              name
              decimals
            }}
            exchanges(where: {{timestamp_gte: {}}}) {{
                boughtId
                tokensBought
                soldId
                tokensSold
            }}
        }}
        }}""".format(yesterday)
    try:
        r = requests.post(graphURL, data=json.dumps(
           {"query": swapsDailyVolumeGraphQuery})
        )
        return r.json()["data"]["swaps"]
    except Exception as e:
        logger.error(f"Error getting data from theGraph: {e}")
        return


btcGraphToChainTokenIdx = [1, 0, 2, 3]
ethGraphToChainTokenIdx = [1, 0]


def get_one_day_volume(tokenPricesUSD, swaps):
    for swap in swaps:
        for exchange in swap["exchanges"]:
            tokenIdx = int(exchange["boughtId"])
            if swap["id"] == btcSwapAddress:
                tokenIdx = btcGraphToChainTokenIdx[tokenIdx]
            elif swap["id"] == vETH2SwapAddress:
                tokenIdx = ethGraphToChainTokenIdx[tokenIdx]
            boughtTokenAddress = swap["tokens"][tokenIdx]["id"]
            if boughtTokenAddress in tokenPricesUSD:
                boughtTokenPrice = tokenPricesUSD[boughtTokenAddress]
            else:
                sys.exit("Price missing for token {}, exiting.".format(
                    boughtTokenAddress
                ))

            boughtTokenAmount = exchange["tokensBought"]
            decimals = int(swap["tokens"][tokenIdx]["decimals"])
            payload.setdefault(swap["id"], dict(EMPTY_PAYLOAD_ITEM))
            payload[swap["id"]]["oneDayVolume"] += (
                float(boughtTokenPrice) * int(boughtTokenAmount)
            ) / (10 ** decimals)


def get_swap_tvls(tokenPricesUSD, swaps):
    for swap in swaps:
        for idx, token in enumerate(swap["tokens"]):
            priceUSD = tokenPricesUSD[token["id"]]
            decimals = int(token["decimals"])
            if swap["id"] == btcSwapAddress:
                idx = btcGraphToChainTokenIdx[idx]
            elif swap["id"] == vETH2SwapAddress:
                idx = ethGraphToChainTokenIdx[idx]
            balance = int(swap["balances"][idx])
            payload.setdefault(swap["id"], dict(EMPTY_PAYLOAD_ITEM))
            payload[swap["id"]]["TVL"] += (balance * priceUSD) / (10**decimals)


def calculate_apys():
    feePercent = 0.0004
    for _, swap in payload.items():
        swap["APY"] = ((1 + (feePercent * swap["oneDayVolume"] / swap["TVL"])) ** 365) - 1 # APY
        # swap["APY"] = (swap["oneDayVolume"] * feePercent * 365) / swap["TVL"] # APR
    return


def write_to_ipfs():
    fleek_aws_client = get_fleek_client(FLEEK_KEY_ID, FLEEK_KEY)

    payload_bytes = json.dumps(payload).encode("utf-8")

    try:
        fleek_aws_client.put_object(
            Bucket=FLEEK_BUCKET, Key=SWAP_STATS_FILE_PATH, Body=payload_bytes
        )
        logger.info(
            "Uploaded apy/volume/tvl to Fleek"
        )
    except Exception as e:
        logger.error(f"Error uploading file: {e}")


def get_token_addresses(swaps):
    tokenAddresses = list()
    for swap in swaps:
        for token in swap["tokens"]:
            tokenAddresses.append(token["id"].lower())
    return tokenAddresses


def main():
    swapsData = get_graph_data()
    if swapsData is None:
        return
    tokenAddresses = get_token_addresses(swapsData)
    print("Using token addresses: {}".format(tokenAddresses))
    tokenPricesUSD = get_token_prices_usd(tokenAddresses)
    print("Using token prices: {}".format(tokenPricesUSD))
    if tokenPricesUSD is None:
        return
    get_one_day_volume(tokenPricesUSD, swapsData)
    get_swap_tvls(tokenPricesUSD, swapsData)
    calculate_apys()
    write_to_ipfs()


if __name__ == "__main__":
    main()
