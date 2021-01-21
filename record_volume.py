import argparse
import datetime
import decimal
import json
import logging
import os
import requests

import web3

from util import get_fleek_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

DAILY_VOL_FILE_PATH = os.environ["DAILY_VOL_FILE_PATH"]
# IMPORTANT: Use checksummed addresses here
SWAP_CONTRACT_ADDRESS = os.environ["SWAP_CONTRACT_ADDRESS"]
HTTP_PROVIDER_URL = os.environ["HTTP_PROVIDER_URL"]
FLEEK_KEY_ID = os.environ["FLEEK_KEY_ID"]
FLEEK_KEY = os.environ["FLEEK_KEY"]
FLEEK_BUCKET = os.environ["FLEEK_BUCKET"]

ETHERSCAN_ENDPOINT = "https://api.etherscan.io/api?module=block&action=getblocknobytime&timestamp={}&closest=before"
SWAP_CONTRACT_ABI_PATH = "Swap.json"
# Recent block number + a buffer
ETH_BLOCKS_IN_A_DAY = 6533 + 1000

TOKEN_DECIMALS = [
    # TBTC
    18,
    # WBTC
    8,
    # RENBTC,
    8,
    # SBTC
    18,
]

event_block_cache = {}


def get_day_ago_block_number():
    now = datetime.datetime.now()
    day_ago = datetime.timedelta(days=1)
    cutoff_dt = now - day_ago
    cutoff_ts = round(cutoff_dt.timestamp())
    try:
        response = requests.get(ETHERSCAN_ENDPOINT.format(cutoff_ts)).json()
        return int(response["result"])

    except Exception as e:
        logger.error(e)


def main(args):
    try:
        f = open(SWAP_CONTRACT_ABI_PATH)
        swap_contract_artifact = json.loads(f.read())
        swap_contract_abi = swap_contract_artifact["abi"]
    except Exception as e:
        logger.error(f"Could not load swap contract ABI: {e}")

    w3 = web3.Web3(web3.Web3.HTTPProvider(HTTP_PROVIDER_URL))

    day_ago_block_number = get_day_ago_block_number()

    contract = w3.eth.contract(abi=swap_contract_abi, address=SWAP_CONTRACT_ADDRESS)
    swaps = contract.events.TokenSwap.createFilter(fromBlock=day_ago_block_number)

    fleek_aws_client = get_fleek_client(FLEEK_KEY_ID, FLEEK_KEY)

    total_tokens_sold = 0
    try:
        all_events = swaps.get_all_entries()
        len_events = len(all_events)

        logger.info(f"Fetched {len_events} events.")
        for event in all_events:
            decimals = TOKEN_DECIMALS[event.args.soldId]
            token_amount = decimal.Decimal(event.args.tokensSold) / (
                decimal.Decimal(10) ** decimals
            )
            total_tokens_sold += token_amount

        payload = {"totalTokens": float(total_tokens_sold), "swaps": len_events}
        logger.info(f"Uploading payload: {payload}")
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        fleek_aws_client.put_object(
            Bucket=FLEEK_BUCKET, Key=DAILY_VOL_FILE_PATH, Body=payload_bytes
        )
        logger.info("Uploaded payload.")

    except Exception as e:
        logger.error(f"Error occurred trying to fetch events and upload: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    args = parser.parse_args()
    main(args)
