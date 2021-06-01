import requests
import json
import logging
import time
import os

from util import get_fleek_client

APY_TVL_VOL_FILE_PATH = os.environ["APY_TVL_VOL_FILE_PATH"]
FLEEK_KEY_ID = os.environ["FLEEK_KEY_ID"]
FLEEK_KEY = os.environ["FLEEK_KEY"]
FLEEK_BUCKET = os.environ["FLEEK_BUCKET"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

stableSwapAddress = "0x3911f80530595fbd01ab1516ab61255d75aeb066"
btcSwapAddress = "0x4f6a43ad7cba042606decaca730d4ce0a57ac62e"
vETH2SwapAddress = "0xdec2157831d6abc3ec328291119cc91b337272b5"

tokenAddrToCoinGeckoID = {
    "0x76204f8CFE8B95191A3d1CfA59E267EA65e06FAC".lower(): "saddleusd",
    "0xC28DF698475dEC994BE00C9C9D8658A548e6304F".lower(): "saddlebtc",
    "0xe37E2a01feA778BC1717d72Bd9f018B6A6B241D5".lower(): "saddleveth2",
    "0x6b175474e89094c44da98b954eedeac495271d0f".lower(): "dai",
    "0xa0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48".lower(): "usd-coin",
    "0xdac17f958d2ee523a2206206994597c13d831ec7".lower(): "tether",
    "0x8daebade922df735c38c80c7ebd708af50815faa".lower(): "tbtc",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599".lower(): "wrapped-bitcoin",
    "0xeb4c2781e4eba804ce9a9803c67d0893436bb27d".lower(): "renbtc",
    "0xfe18be6b3bd88a2d2a7f928d00292e7a9963cfc6".lower(): "sbtc",
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2".lower(): "ethereum",
    "0x898BAD2774EB97cF6b94605677F43b41871410B1".lower(): "ethereum"
}

tokenAddresses = [
    "0x76204f8CFE8B95191A3d1CfA59E267EA65e06FAC",
    "0xC28DF698475dEC994BE00C9C9D8658A548e6304F",
    "0xe37E2a01feA778BC1717d72Bd9f018B6A6B241D5",
    "0x6b175474e89094c44da98b954eedeac495271d0f",
    "0xa0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "0xdac17f958d2ee523a2206206994597c13d831ec7",
    "0x8daebade922df735c38c80c7ebd708af50815faa",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
    "0xeb4c2781e4eba804ce9a9803c67d0893436bb27d",
    "0xfe18be6b3bd88a2d2a7f928d00292e7a9963cfc6",
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    "0x898BAD2774EB97cF6b94605677F43b41871410B1",
]

payload = {
    stableSwapAddress: {
        "oneDayVolume": 0,
        "APY": 0,
        "TVL": 0,
    },
    btcSwapAddress: {
        "oneDayVolume": 0,
        "APY": 0,
        "TVL": 0,
    },
    vETH2SwapAddress: {
        "oneDayVolume": 0,
        "APY": 0,
        "TVL": 0,
    },
}


def getTokenPricesUSD():
    tokenPricesUSD = dict()
    CGTokenNames = ["saddlebtc", "saddleusd", "saddleveth2", "dai", "usd-coin",
                    "tether",  "tbtc", "wrapped-bitcoin", "renbtc", "sbtc",
                    "ethereum"]

    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids={}&vs_currencies=usd".format(','.join(CGTokenNames)))
    except Exception as e:
        logger.error(f"Error getting price data from coinGecko: {e}")

    for token, price in r.json().items():
        tokenPricesUSD[token] = float(price["usd"])

    return tokenPricesUSD


def getGraphData():
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
            exchanges(timestamp_gte: {}) {{
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


def getOneDayVolume(tokenPricesUSD, swaps):
    for swap in swaps:
        for exchange in swap["exchanges"]:
            tokenIdx = int(exchange["boughtId"])
            if swap["id"] == btcSwapAddress:
                tokenIdx = btcGraphToChainTokenIdx[tokenIdx]
            elif swap["id"] == vETH2SwapAddress:
                tokenIdx = ethGraphToChainTokenIdx[tokenIdx]
            boughtTokenAddress = swap["tokens"][tokenIdx]["id"]
            boughtTokenCoinGeckoID = tokenAddrToCoinGeckoID[boughtTokenAddress]
            boughtTokenPrice = tokenPricesUSD[boughtTokenCoinGeckoID]
            boughtTokenAmount = exchange["tokensBought"]
            decimals = int(swap["tokens"][tokenIdx]["decimals"])
            payload[swap["id"]]["oneDayVolume"] += (float(boughtTokenPrice) * int(boughtTokenAmount)) / (10 ** decimals)


def getSwapTLVs(tokenPricesUSD, swaps):
    for swap in swaps:
        for idx, token in enumerate(swap["tokens"]):
            coinGeckoID = tokenAddrToCoinGeckoID[token["id"]]
            priceUSD = tokenPricesUSD[coinGeckoID]
            decimals = int(token["decimals"])
            if swap["id"] == btcSwapAddress:
                idx = btcGraphToChainTokenIdx[idx]
            elif swap["id"] == vETH2SwapAddress:
                idx = ethGraphToChainTokenIdx[idx]
            balance = int(swap["balances"][idx])
            payload[swap["id"]]["TVL"] += (balance * priceUSD) / (10**decimals)


def calculateAPYs():
    feePercent = 0.0004
    for _, swap in payload.items():
        swap["APY"] = (swap["oneDayVolume"] * feePercent * 365) / swap["TVL"]
    return


def writeToIPFS():
    fleek_aws_client = get_fleek_client(FLEEK_KEY_ID, FLEEK_KEY)

    payload_bytes = json.dumps(payload).encode("utf-8")

    try:
        fleek_aws_client.put_object(
            Bucket=FLEEK_BUCKET, Key=APY_TVL_VOL_FILE_PATH, Body=payload_bytes
        )
        logger.info(
            "Uploaded apy/volume/tvl to Fleek"
        )
    except Exception as e:
        logger.error(f"Error uploading file: {e}")


def main():
    tokenPricesUSD = getTokenPricesUSD()
    if tokenPricesUSD is None:
        return
    swapsData = getGraphData()
    if swapsData is None:
        return
    getOneDayVolume(tokenPricesUSD, swapsData)
    getSwapTLVs(tokenPricesUSD, swapsData)
    calculateAPYs()
    writeToIPFS()


if __name__ == "__main__":
    main()
