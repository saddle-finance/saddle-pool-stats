import requests
import json
import logging
import time
import os
from dotenv import load_dotenv
from util import get_fleek_client
from multicall import Call, Multicall
from web3 import Web3

load_dotenv()

SWAP_STATS_FILE_PATH = os.environ["SWAP_STATS_FILE_PATH"]
FLEEK_KEY_ID = os.environ["FLEEK_KEY_ID"]
FLEEK_KEY = os.environ["FLEEK_KEY"]
FLEEK_BUCKET = os.environ["FLEEK_BUCKET"]
ALCHEMY_API_KEY = os.environ["ALCHEMY_API_KEY"]
NUM_DAYS_TO_AVG = 2
def identity(x):
    return x

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

MAINNET = {
    "name": "mainnet",
    "chain_id": 1,
    "subgraph": "saddle",
    "rpc_url": f"https://eth-mainnet.alchemyapi.io/v2/{ALCHEMY_API_KEY}"
}
ARBITRUM = {
    "name": "arbitrum",
    "chain_id": 42161,
    "subgraph": "saddle-arbitrum",
    "rpc_url": f"https://arb-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
}
OPTIMISM = {
    "name": "optimism",
    "chain_id": 10,
    "subgraph": "optimism",
    "rpc_url": f"https://opt-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
}

SUPPORTED_NETWORKS = [MAINNET, ARBITRUM, OPTIMISM]

EMPTY_PAYLOAD_ITEM = {
    "oneDayVolume": 0,
    "APY": 0,
    "TVL": 0,
}

def get_token_type_by_name(name):
    name = name.upper()
    major_types = ["USD", "BTC", "ETH"]
    return name if name in major_types else "USD"


def get_token_prices_usd():
    tokenPricesUSD = dict()
    tokenIds = ["bitcoin", "ethereum"]

    try:
        url = ("https://api.coingecko.com/api/v3/simple/price"
               "?ids={}"
               "&vs_currencies=usd""".format(','.join(tokenIds)))
        r = requests.get(url)
    except Exception as e:
        logger.error(f"Error getting price data from coinGecko: {e}")
        return
    response_dict = r.json()
    for gecko_id, price in response_dict.items():
        if price == {}:
            logger.error("Error getting price data for token: {}".format(
                gecko_id
            ))
        else:
            key = "BTC" if gecko_id == "bitcoin" else "ETH"
            tokenPricesUSD[key] = float(price["usd"])
        tokenPricesUSD["USD"] = 1
    return tokenPricesUSD


def get_graph_data(subgraph):
    graphURL = f"https://api.thegraph.com/subgraphs/name/saddle-finance/{subgraph}"
    yesterday = int(time.time()) - 3600*24*NUM_DAYS_TO_AVG
    swapsDailyVolumeGraphQuery = """{{
        swaps {{
            address
            balances
            swapFee
            tokens {{
              address
              name
              decimals
            }}
            hourlyVolumes(where: {{timestamp_gte: {}}}, orderBy: timestamp, orderDirection: desc) {{
                volume
                timestamp
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


def get_pool_token_positions(network, swaps):
    w3 = Web3(Web3.HTTPProvider(network["rpc_url"]))
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
        logger.error(f"\nError getting pool token positions: {e}")
        return

def get_one_day_volume(tokenPricesUSD, graph_data):
    result = {}
    for swap in graph_data:
        result.setdefault(swap["address"], dict(EMPTY_PAYLOAD_ITEM))

        # assemble to pool name for printing
        token_names = [token["name"] for token in swap["tokens"]]
        pool_name = ", ".join(token_names)
        print(f"\n{swap['address']} [{pool_name}]")

        pool_type = get_token_type_by_name(swap["tokens"][0]["name"])
        asset_price = tokenPricesUSD[pool_type]

        total_volume = 0.0
        for hourly_volume in swap["hourlyVolumes"]:
            total_volume += float(hourly_volume["volume"])

        result[swap['address']]['oneDayVolume'] = total_volume * asset_price
        sum_amount = f"${result[swap['address']]['oneDayVolume']:,.0f}"
        print(f"{'Volume'} {sum_amount:>14}")
        result[swap["address"]]["oneDayVolume"] /= NUM_DAYS_TO_AVG

    return result


def get_swap_tvls(payload, tokenPricesUSD, graph_data, poolTokenPositions):
    for swap in graph_data:
        pool_type = get_token_type_by_name(swap["tokens"][0]["name"])
        asset_price = tokenPricesUSD[pool_type]
        for idx, token in enumerate(swap["tokens"]):
            decimals = int(token["decimals"])
            tokenIdx = poolTokenPositions[swap["address"]][idx]
            balance = int(swap["balances"][tokenIdx])
            payload.setdefault(swap["address"], dict(EMPTY_PAYLOAD_ITEM))
            payload[swap["address"]]["TVL"] += (balance * asset_price) / (10**decimals)
    return payload


def calculate_apys(payload, graph_data):
    swap_fees = {}
    swap_fees.setdefault(0.0004)
    for swap in graph_data:
        swap_fees[swap["address"]] = int(swap["swapFee"]) / (10**10)

    for key, swap in payload.items():
        fee_pct = swap_fees[key]
        swap["APY"] = 0 if swap["TVL"] == 0 else ((1 + (fee_pct * swap["oneDayVolume"] / swap["TVL"])) ** 365) - 1 # APY
    return payload


def write_to_ipfs(payload):
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
    tokenPricesUSD = get_token_prices_usd()
    print("\n/********** Token Prices **********/")
    print("\n".join(list(map(lambda pair: f"{pair[0]:<25} {pair[1]:>10,.2f}", sorted(tokenPricesUSD.items(), key=lambda pair: pair[1])))))
    if tokenPricesUSD is None:
        return

    all_networks_payloads = {}
    for network in SUPPORTED_NETWORKS:
        graph_data = get_graph_data(network["subgraph"])
        if graph_data is None:
            return
        
        pool_token_positions = get_pool_token_positions(network, graph_data)
        tokenAddresses = get_token_addresses(graph_data)
        print(f"\n/********** {network['name']} Token Addresses **********/")
        print("\n".join(list(map(lambda pair: f"{pair[1]:<25} {pair[0]}", sorted(tokenAddresses.items(), key=lambda pair: pair[1].lower())))))

        print(f"\n/********** {network['name']} Exchanges of {NUM_DAYS_TO_AVG} Days **********/")
        payload = get_one_day_volume(tokenPricesUSD, graph_data)
        payload = get_swap_tvls(payload, tokenPricesUSD, graph_data, pool_token_positions)    
        payload = calculate_apys(payload, graph_data)
        all_networks_payloads[network["chain_id"]] = payload
        print(f"\n/********** {network['name']} Final Result (avg of {NUM_DAYS_TO_AVG} days) **********/")
        print(f"{'Address':<50} {'APY':<10} {'Volume':<10} {'TVL':<13}")
        for address, data in sorted(payload.items(), key=lambda pair: pair[1]["TVL"], reverse=True):
            print(f"{address:<50} {data['APY']:<10.4f} {int(data['oneDayVolume']):>10,d} {int(data['TVL']):>13,d}")
    
    write_to_ipfs({
      "seconds_since_epoch": round(time.time()),
      **all_networks_payloads,
    })


if __name__ == "__main__":
    main()
