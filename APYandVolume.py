import requests
import json
import time

class Swap:
    def __init__(self, name, tokens):
        self.apy = 0 #TODO calculate I think it's just 0.004 * volume * 365 / TVL
        self.volume = 0
        self.name = name
        self.tokenList = tokens
        self.tlv = 0 # todo get balanceOf each pool using web3 or ethers

# pool addresses (We call them swaps):
stableSwapAddress = "0x3911f80530595fbd01ab1516ab61255d75aeb066"
btcSwapAddress = "0x4f6a43ad7cba042606decaca730d4ce0a57ac62e"
vETH2SwapAddress = "0xdec2157831d6abc3ec328291119cc91b337272b5"

def getTokenPricesUSD(tokenPricesUSD):
    CGTokenNames = ["saddlebtc", "saddleusd", "saddleveth2", "dai", "usd-coin", "tether",  "tbtc", "wrapped-bitcoin", "renbtc", "sbtc", "weth"]

    r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids={}&vs_currencies=usd".format(','.join(CGTokenNames)))

    for token, price in r.json().items():
        tokenPricesUSD[token] = price["usd"]

def get24HrVolume(tokenPricesUSD, swaps):
    graphURL = "https://api.thegraph.com/subgraphs/name/saddle-finance/saddle"
    yesterday = int(time.time()) - 3600*24
    swapsGraphQuery = """{{
    swaps {{
        address
        exchanges(first: 1) {{
        boughtId
        tokensBought
        soldId
        tokensSold
        }}
    }}
    }}""".format(yesterday)

    r = requests.post(graphURL, data=json.dumps({"query": swapsGraphQuery}))

    for swap in r.json()["data"]["swaps"]:
        currentPool = swaps[swap["address"]]
        for exchange in swap["exchanges"]:
            boughtToken = currentPool.tokenList[int(exchange["boughtId"])]
            tokenAmount = 0
            tokenPrice = 0
            # If we're in the VETH pool we don't have a price for VETH2, so make sure to use WETH 
            if swap["address"] == vETH2SwapAddress:
                # if the token bought was wETH we can use the price and amount
                tokenPrice = tokenPricesUSD[currentPool.tokenList[0]]
                if exchange["boughtId"] == "0":
                    tokenAmount = exchange["tokensBought"] # this number has no decimal, need to math
                else:
                    tokenAmount = exchange["tokensSold"] # this number has no decimal, need to math
            else:
                tokenPrice = tokenPricesUSD[boughtToken]
                tokenAmount = int(exchange["tokensBought"])
            
            currentPool.volume += float(tokenPrice) * int(tokenAmount)

def getSwapTLVs(swaps):
    # todo implement this using web3 or ethers, using balanceOf method
    return

def calculateAPYs(swaps):
    # todo implement this - for MVP use constant fee? Or pull from thegraph?
    feePercent = 0.4
    for _, swap in swaps:
        swap.apy = feePercent * 0.01 * 365 / swap.tlv
    return 

def main():
    stableSwapCoins = ["dai", "usd-coin", "tether"]
    btcSwapCoins = ["tbtc", "wrapped-bitcoin", "renbtc", "sbtc"]
    vETHSwapCoins = ["weth", "veth2"]

    swaps = {
        stableSwapAddress: Swap("Stable", stableSwapCoins),
        btcSwapAddress: Swap("Btc", btcSwapCoins),
        vETH2SwapAddress: Swap("vETH2", vETHSwapCoins)
    }

    tokenPricesUSD = dict()
    getTokenPricesUSD(tokenPricesUSD)
    get24HrVolume(tokenPricesUSD, swaps)
    #getSwapTLVs(swaps)

    # Todo write to json file instead of logging
    for address, swap in swaps.items():
        print("pool: {} volume: {} apy: {}".format(swap.name, swap.volume, swap.apy))
    
if __name__ == "__main__":
    main()
            


    
