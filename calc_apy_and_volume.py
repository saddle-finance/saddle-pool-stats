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
NUM_DAYS_TO_AVG = 2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

usdV2SwapAddress = "0xaCb83E0633d6605c5001e2Ab59EF3C745547C8C7".lower()
btcV2SwapAddress = "0xdf3309771d2BF82cb2B6C56F9f5365C8bD97c4f2".lower()

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

def get_token_type_by_name(name):
    if "usd" in name.lower():
        return "USD"
    elif "btc" in name.lower():
        return "BTC"
    elif "eth" in name.lower():
        return "ETH"
    else:
        return "USD" # frax etc

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
            token_type = get_token_type_by_name(name)
            if token_type == "USD":
                tokenPricesUSD[tokenAddress] = 1
            elif token_type == "BTC":
                tokenPricesUSD[tokenAddress] = tokenPricesUSD[WBTCTokenAddress]
            elif token_type == "ETH":
                tokenPricesUSD[tokenAddress] = tokenPricesUSD[WETHTokenAddress]
    return tokenPricesUSD


def get_graph_data():
    graphURL = "https://api.thegraph.com/subgraphs/name/saddle-finance/saddle"
    yesterday = int(time.time()) - 3600*24*NUM_DAYS_TO_AVG
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
                __typename
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
        payload.setdefault(swap["address"], dict(EMPTY_PAYLOAD_ITEM))

        # assemble to pool name for printing
        token_names = [token["name"] for token in swap["tokens"]]
        token_positions = poolTokenPositions[swap["address"]]
        sorted_token_names = [x[1] for x in sorted(zip(token_positions, token_names))]
        pool_name = ", ".join(sorted_token_names)
        print(f"\n{swap['address']} Volume [{pool_name}]")

        pool_type = get_token_type_by_name(swap["tokens"][0]["name"])

        token_idx = None
        bought_token_address = None
        decimals = None
        bought_token_price = None
        for exchange in swap["exchanges"]:
            bought_idx = int(exchange["boughtId"])
            if exchange["__typename"] == "TokenExchange":
                token_idx = poolTokenPositions[swap["address"]][bought_idx]
                bought_token_address = swap["tokens"][token_idx]["address"]
                decimals = int(swap["tokens"][token_idx]["decimals"])
            else: # case for TokenExchangeUnderlying
                underlying_pool_address = None
                if pool_type == "USD":
                    underlying_pool_address = usdV2SwapAddress
                elif pool_type == "BTC":
                    underlying_pool_address = btcV2SwapAddress
                else:
                    sys.exit("Unsupported pool type")
                underlying_swap = [swap for swap in swaps if swap["address"] == underlying_pool_address][0]
                if bought_idx == 0:
                    bought_token_address = swap["tokens"][0]["address"]
                    decimals = int(swap["tokens"][0]["decimals"])
                else:
                    token_idx = poolTokenPositions[underlying_pool_address][bought_idx - 1]
                    bought_token_address = underlying_swap["tokens"][token_idx]["address"]
                    decimals = int(underlying_swap["tokens"][token_idx]["decimals"])
            if bought_token_address in tokenPricesUSD:
                bought_token_price = tokenPricesUSD[bought_token_address]
            else:
                sys.exit(f"Price missing for token {bought_token_address}, exiting.")

            bought_token_amount = exchange["tokensBought"]
            parsed_amount = (
                float(bought_token_price) * int(bought_token_amount)
            ) / (10 ** decimals)
            payload[swap["address"]]["oneDayVolume"] += parsed_amount
            txn = exchange["transaction"]
            dollar_amount = f"${int(parsed_amount):,}"
            print(f"{txn} {dollar_amount:>14}")
        sum_amount = f"${payload[swap['address']]['oneDayVolume']:,.0f}"
        print(f"{'Sum':>66} {sum_amount:>14}")
        payload[swap["address"]]["oneDayVolume"] /= NUM_DAYS_TO_AVG


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
    print("\n".join(list(map(lambda pair: f"{pair[1]:<25} {pair[0]}", sorted(tokenAddresses.items(), key=lambda pair: pair[1].lower())))))

    tokenPricesUSD = get_token_prices_usd(tokenAddresses)
    print("\n/********** Token Prices **********/")
    print("\n".join(list(map(lambda pair: f"{tokenAddresses[pair[0]]:<25} {pair[1]:>10,.3f}", sorted(tokenPricesUSD.items(), key=lambda pair: pair[1])))))
    if tokenPricesUSD is None:
        return
    print(f"\n/********** Exchanges of {NUM_DAYS_TO_AVG} Days **********/")
    get_one_day_volume(tokenPricesUSD, swapsData, pool_token_positions)
    get_swap_tvls(tokenPricesUSD, swapsData, pool_token_positions)    
    calculate_apys()
    print(f"\n/********** Final Result (avg of {NUM_DAYS_TO_AVG} days) **********/")
    print(f"{'Address':<50} {'APY':<10} {'Volume':<10} {'TVL':<13}")
    for address, data in sorted(payload.items(), key=lambda pair: pair[1]["TVL"], reverse=True):
        print(f"{address:<50} {data['APY']:<10.4f} {int(data['oneDayVolume']):>10,d} {int(data['TVL']):>13,d}")
    write_to_ipfs()


if __name__ == "__main__":
    main()