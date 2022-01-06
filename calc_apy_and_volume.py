import requests
import json
import logging
import time
import os
import sys
from dotenv import load_dotenv
from util import get_fleek_client
from multicall import Call, Multicall
from web3 import Web3

load_dotenv()

SWAP_STATS_FILE_PATH = os.environ["SWAP_STATS_FILE_PATH"]
FLEEK_KEY_ID = os.environ["FLEEK_KEY_ID"]
FLEEK_KEY = os.environ["FLEEK_KEY"]
FLEEK_BUCKET = os.environ["FLEEK_BUCKET"]
HTTP_PROVIDER_URL = os.environ["HTTP_PROVIDER_URL"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

stableSwapAddress = "0x3911f80530595fbd01ab1516ab61255d75aeb066"
btcSwapAddress = "0x4f6a43ad7cba042606decaca730d4ce0a57ac62e"
vETH2SwapAddress = "0xdec2157831d6abc3ec328291119cc91b337272b5"

# coingecko api accepts case insensitive but returns lowercase addresses
WETHTokenAddress = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2".lower()
WBTCTokenAddress = "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599".lower()

payload = {}
EMPTY_PAYLOAD_ITEM = {
    "oneDayVolume": 0,
    "APY": 0,
    "TVL": 0,
}

def get_pool_token_positions(swaps):
    w3 = Web3(Web3.HTTPProvider(HTTP_PROVIDER_URL))
    identity = lambda x: x
    calls = []
    # get token positions for each pool
    for pool in swaps:
        for token in pool['tokens']:
            calls.append(
                Call(
                    pool['address'], 
                    ['getTokenIndex(address)(uint8)', token['address']], 
                    [[f"{pool['address']}_{token['address']}", identity]]
                )
            )
    try:
        # execute the call
        multi = Multicall(calls, _w3=w3)
        response = multi()

        # parse the response
        poolTokenPositions = dict()
        for pool in swaps:
            idxs = [None] * len(pool['tokens'])
            for i, token in enumerate(pool['tokens']):
                idxs[i] = response[f"{pool['address']}_{token['address']}"]
            poolTokenPositions[pool['address']] = idxs
        return poolTokenPositions
    except Exception as e:
        logger.error(f"Error getting pool token positions: {e}")
        return


def get_token_prices_usd(tokens):
    tokenAddresses = tokens.keys()
    tokenPricesUSD = dict()

    try:
        url = ("https://api.coingecko.com/api/v3/simple/token_price"
               "/ethereum?contract_addresses={}"
               "&vs_currencies=usd""".format(','.join(tokenAddresses)))
        r = requests.get(url)
    except Exception as e:
        logger.error(f"Error getting price data from coinGecko: {e}")
        return
    response_dict = r.json()
    for tokenAddress, price in response_dict.items():
        if price == {}:
            logger.error("Error getting price data for token: {}".format(
                tokens[tokenAddress]
            ))
        else:
            tokenPricesUSD[tokenAddress] = float(price["usd"])
    for tokenAddress, name in tokens.items():
        if tokenAddress not in tokenPricesUSD:
            if "usd" in name.lower():
                tokenPricesUSD[tokenAddress] = 1
            elif "btc" in name.lower():
                tokenPricesUSD[tokenAddress] = tokenPricesUSD[WBTCTokenAddress]
            elif "eth" in name.lower():
                tokenPricesUSD[tokenAddress] = tokenPricesUSD[WETHTokenAddress]
            else:
                tokenPricesUSD[tokenAddress] = 1
    return tokenPricesUSD


def get_graph_data():
    graphURL = "https://api.thegraph.com/subgraphs/name/saddle-finance/saddle"
    yesterday = int(time.time()) - 3600*24
    swapsDailyVolumeGraphQuery = """{{
        swaps {{
            address
            balances
            tokens {{
              address
              name
              decimals
            }}
            exchanges(where: {{timestamp_gte: {}}}, orderBy: tokensBought, orderDirection: desc) {{
                boughtId
                tokensBought
                soldId
                tokensSold
                transaction
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


def get_one_day_volume(tokenPricesUSD, swaps, poolTokenPositions):
    for swap in swaps:
        print("\nProcessing {} volume".format(swap["address"]))
        for exchange in swap["exchanges"]:
            try:
                tokenIdx = int(exchange["boughtId"])
                tokenIdx = poolTokenPositions[swap["address"]][tokenIdx]
                boughtTokenAddress = swap["tokens"][tokenIdx]["address"]
            # for metapools fallback to using the first token to calculate price
            except IndexError:
                tokenIdx = 0
                boughtTokenAddress = swap["tokens"][tokenIdx]["address"]
            if boughtTokenAddress in tokenPricesUSD:
                boughtTokenPrice = tokenPricesUSD[boughtTokenAddress]
            else:
                sys.exit("Price missing for token {}, exiting.".format(
                    boughtTokenAddress
                ))

            boughtTokenAmount = exchange["tokensBought"]
            decimals = int(swap["tokens"][tokenIdx]["decimals"])
            payload.setdefault(swap["address"], dict(EMPTY_PAYLOAD_ITEM))
            parsed_amount = (
                float(boughtTokenPrice) * int(boughtTokenAmount)
            ) / (10 ** decimals)
            payload[swap["address"]]["oneDayVolume"] += parsed_amount
            txn = exchange["transaction"]
            print(f"{txn} swapped ${int(parsed_amount):>12,d}")


def get_swap_tvls(tokenPricesUSD, swaps, poolTokenPositions):
    for swap in swaps:
        for idx, token in enumerate(swap["tokens"]):
            priceUSD = tokenPricesUSD[token["address"]]
            decimals = int(token["decimals"])
            tokenIdx = poolTokenPositions[swap["address"]][idx]
            balance = int(swap["balances"][tokenIdx])
            payload.setdefault(swap["address"], dict(EMPTY_PAYLOAD_ITEM))
            payload[swap["address"]]["TVL"] += (balance * priceUSD) / (10**decimals)


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
    map = dict()
    for swap in swaps:
        for token in swap["tokens"]:
            map[token["address"].lower()] = token["name"]
    return map


def main():
    swapsData = get_graph_data()
    if swapsData is None:
        return
    pool_token_positions = get_pool_token_positions(swapsData)
    tokenAddresses = get_token_addresses(swapsData)
    print("\n/********** Token Addresses **********/")
    print("\n".join(list(map(lambda pair: f"{pair[1]:<25} {pair[0]}", tokenAddresses.items()))))

    tokenPricesUSD = get_token_prices_usd(tokenAddresses)
    print("\n/********** Token Prices **********/")
    print("\n".join(list(map(lambda pair: f"{tokenAddresses[pair[0]]:<25} {pair[1]:>10,.3f}", sorted(tokenPricesUSD.items(), key=lambda pair: pair[1])))))
    if tokenPricesUSD is None:
        return
    print("\n/********** Exchanges **********/")
    get_one_day_volume(tokenPricesUSD, swapsData, pool_token_positions)
    get_swap_tvls(tokenPricesUSD, swapsData, pool_token_positions)    
    calculate_apys()
    print("\n/********** Final Result **********/")
    print(f"{'Address':<50} {'APY':<10} {'Volume':<10} {'TVL':<13}")
    for address, data in sorted(payload.items(), key=lambda pair: pair[1]["TVL"], reverse=True):
        print(f"{address:<50} {data['APY']:<10.4f} {int(data['oneDayVolume']):>10,d} {int(data['TVL']):>13,d}")
    write_to_ipfs()


if __name__ == "__main__":
    main()
