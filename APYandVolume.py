import requests
import json
import time

class Swap:
    def __init__(self, name, tokens):
        self.apy = 0 #TODO calculate I think it's just 0.004 * volume * 365 / TVL
        self.oneDayVolume = 0
        self.name = name
        self.tokenList = tokens
        self.tlv = 0 # todo get balanceOf each pool using web3 or ethers

class Token:
    def __init__(self, decimals, symbol, geckoId, name):
        self.symbol = symbol
        self.name = name
        self.geckoId = geckoId
        self.decimals = decimals

BTC_SWAP_TOKEN = Token(
  18,
  "saddleBTC",
  "saddlebtc",
  "Saddle TBTC/WBTC/RENBTC/SBTC")

STABLECOIN_SWAP_TOKEN = Token(
  18,
  "saddleUSD",
  "saddleusd",
  "Saddle DAI/USDC/USDT")

VETH2_SWAP_TOKEN = Token(
  18,
  "saddleVETH2",
  "saddleveth2",
  "Saddle WETH/vETH2")

DAI = Token(18,
  "DAI",
  "dai",
  "Dai")
USDC = Token(6,
  "USDC",
  "usd-coin",
  "USDC Coin")
USDT = Token(6,
  "USDT",
  "tether",
  "Tether")
WBTC = Token(8,
  "WBTC",
  "wrapped-bitcoin",
  "WBTC")
TBTC = Token(18,
  "TBTC",
  "tbtc",
  "tBTC")
RENBTC = Token(8,
  "RENBTC",
  "renbtc",
  "renBTC")
SBTC = Token(18,
  "SBTC",
  "sbtc",
  "sBTC",)
VETH2 = Token(18,
  "VETH2",
  "ethereum",
  "vETH2")
WETH = Token(18,
  "WETH",
  "ethereum",
  "WETH")

stableSwapTokens = [DAI, USDC, USDT]
btcSwapTokens = [TBTC, WBTC, RENBTC, SBTC]
vETHSwapTokens = [WETH, VETH2]

# pool addresses (We call them swaps):
stableSwapAddress = "0x3911f80530595fbd01ab1516ab61255d75aeb066"
btcSwapAddress = "0x4f6a43ad7cba042606decaca730d4ce0a57ac62e"
vETH2SwapAddress = "0xdec2157831d6abc3ec328291119cc91b337272b5"

swaps = {
    stableSwapAddress: Swap("Stable", stableSwapTokens),
    btcSwapAddress: Swap("Btc", btcSwapTokens),
    vETH2SwapAddress: Swap("vETH2", vETHSwapTokens)
}


def getTokenPricesUSD():
    tokenPricesUSD = dict()
    CGTokenNames = ["saddlebtc", "saddleusd", "saddleveth2", "dai", "usd-coin", "tether",  "tbtc", "wrapped-bitcoin", "renbtc", "sbtc", "ethereum"]

    r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids={}&vs_currencies=usd".format(','.join(CGTokenNames)))

    for token, price in r.json().items():
        tokenPricesUSD[token] = price["usd"]
    
    return tokenPricesUSD

def getOneDayVolume(tokenPricesUSD):
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
    # print(r.json())
    # return 
    for swap in r.json()["data"]["swaps"]:
        currentPool = swaps[swap["address"]]
        for exchange in swap["exchanges"]:
            boughtToken = currentPool.tokenList[int(exchange["boughtId"])]
            print("Current bought token: {}".format(boughtToken.geckoId))
            tokenAmount = 0
            tokenPrice = 0
            # If we're in the VETH pool we don't have a price for VETH2, so make sure to use WETH 
            if swap["address"] == vETH2SwapAddress:
                # if the token bought was wETH we can use the price and amount
                tokenPrice = tokenPricesUSD[currentPool.tokenList[0].geckoId]
                if exchange["boughtId"] == "0":
                    tokenAmount = exchange["tokensBought"] # this number has no decimal, need to math
                else:
                    tokenAmount = exchange["tokensSold"] # this number has no decimal, need to math
            else:
                tokenPrice = tokenPricesUSD[boughtToken.geckoId]
                tokenAmount = int(exchange["tokensBought"])
            
            currentPool.oneDayVolume += float(tokenPrice) * int(tokenAmount)

def getSwapTLVs():
    # todo implement this using web3 or ethers, using balanceOf method
    return

def calculateAPYs():
    # todo implement this - for MVP use constant fee? Or pull from thegraph?
    feePercent = 0.4
    for _, swap in swaps:
        swap.apy = feePercent * swap.oneDayVolume * 365 / swap.tlv
    return 

def main():
    tokenPricesUSD = getTokenPricesUSD()
    getOneDayVolume(tokenPricesUSD)
    #getSwapTLVs(swaps)

    # Todo write to json file instead of logging
    for address, swap in swaps.items():
        print("pool: {} volume: {} apy: {}".format(swap.name, swap.oneDayVolume, swap.apy))
    
if __name__ == "__main__":
    main()
            


    
