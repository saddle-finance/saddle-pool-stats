import requests
import json
import time

# class Swap:
#     def __init__(self, name, tokens):
#         self.apy = 0 #TODO calculate I think it's just 0.004 * volume * 365 / TVL
#         self.oneDayVolume = 0
#         self.name = name
#         self.tokenList = tokens
#         self.tlv = 0 # todo get balanceOf each pool using web3 or ethers

# class Token:
#     def __init__(self, decimals, symbol, geckoId, name):
#         self.symbol = symbol
#         self.name = name
#         self.geckoId = geckoId
#         self.decimals = decimals

# BTC_SWAP_TOKEN = Token(
#   18,
#   "saddleBTC",
#   "saddlebtc",
#   "Saddle TBTC/WBTC/RENBTC/SBTC")

# STABLECOIN_SWAP_TOKEN = Token(
#   18,
#   "saddleUSD",
#   "saddleusd",
#   "Saddle DAI/USDC/USDT")

# VETH2_SWAP_TOKEN = Token(
#   18,
#   "saddleVETH2",
#   "saddleveth2",
#   "Saddle WETH/vETH2")

# DAI = Token(18,
#   "DAI",
#   "dai",
#   "Dai")
# USDC = Token(6,
#   "USDC",
#   "usd-coin",
#   "USDC Coin")
# USDT = Token(6,
#   "USDT",
#   "tether",
#   "Tether")
# WBTC = Token(8,
#   "WBTC",
#   "wrapped-bitcoin",
#   "WBTC")
# TBTC = Token(18,
#   "TBTC",
#   "tbtc",
#   "tBTC")
# RENBTC = Token(8,
#   "RENBTC",
#   "renbtc",
#   "renBTC")
# SBTC = Token(18,
#   "SBTC",
#   "sbtc",
#   "sBTC",)
# VETH2 = Token(18,
#   "VETH2",
#   "ethereum",
#   "vETH2")
# WETH = Token(18,
#   "WETH",
#   "ethereum",
#   "WETH")

# stableSwapTokens = [DAI, USDC, USDT]
# btcSwapTokens = [TBTC, WBTC, RENBTC, SBTC]
# vETHSwapTokens = [WETH, VETH2]

# pool addresses (We call them swaps):
stableSwapAddress = "0x3911f80530595fbd01ab1516ab61255d75aeb066"
btcSwapAddress = "0x4f6a43ad7cba042606decaca730d4ce0a57ac62e"
vETH2SwapAddress = "0xdec2157831d6abc3ec328291119cc91b337272b5"

tokenAddressToCoinGeckoID = {
  "0x76204f8CFE8B95191A3d1CfA59E267EA65e06FAC".lower(): "saddleusd", # swap coins
  "0xC28DF698475dEC994BE00C9C9D8658A548e6304F".lower(): "saddlebtc",
  "0xe37E2a01feA778BC1717d72Bd9f018B6A6B241D5".lower(): "saddleveth2",
  "0x6b175474e89094c44da98b954eedeac495271d0f".lower(): "dai", # stable coins
  "0xa0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48".lower(): "usd-coin",
  "0xdac17f958d2ee523a2206206994597c13d831ec7".lower(): "tether",
  "0x8daebade922df735c38c80c7ebd708af50815faa".lower(): "tbtc",
  "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599".lower(): "wrapped-bitcoin", # btc coins
  "0xeb4c2781e4eba804ce9a9803c67d0893436bb27d".lower(): "renbtc",
  "0xfe18be6b3bd88a2d2a7f928d00292e7a9963cfc6".lower(): "sbtc",
  "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2".lower(): "ethereum", # eth coins
  "0x898BAD2774EB97cF6b94605677F43b41871410B1".lower(): "ethereum"
}

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
    CGTokenNames = ["saddlebtc", "saddleusd", "saddleveth2", "dai", "usd-coin", "tether",  "tbtc", "wrapped-bitcoin", "renbtc", "sbtc", "ethereum"]

    r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids={}&vs_currencies=usd".format(','.join(CGTokenNames)))

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

  r = requests.post(graphURL, data=json.dumps({"query": swapsDailyVolumeGraphQuery}))
  return r.json()["data"]["swaps"]

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
            boughtTokenCoinGeckoID = tokenAddressToCoinGeckoID[boughtTokenAddress]
            boughtTokenPrice = tokenPricesUSD[boughtTokenCoinGeckoID]
            boughtTokenAmount = exchange["tokensBought"]
            decimals = int(swap["tokens"][tokenIdx]["decimals"])
            payload[swap["id"]]["oneDayVolume"] += (float(boughtTokenPrice) * int(boughtTokenAmount)) / (10 ** decimals)

def getSwapTLVs(tokenPricesUSD, swaps):
    for swap in swaps:
      for idx, token in enumerate(swap["tokens"]):
        coinGeckoID = tokenAddressToCoinGeckoID[token["id"]]
        priceUSD = tokenPricesUSD[coinGeckoID]
        decimals = int(token["decimals"])
        if swap["id"] == btcSwapAddress:
          idx = btcGraphToChainTokenIdx[idx]
        elif swap["id"] == vETH2SwapAddress:
          idx = ethGraphToChainTokenIdx[idx]
        balance = int(swap["balances"][idx])
        print("adding {} {} which cost {} and has {} decimals to the swap TVL".format(balance, coinGeckoID, priceUSD, decimals))
        payload[swap["id"]]["TVL"] += (balance * priceUSD) / (10**decimals)

def calculateAPYs():
    feePercent = 0.04
    for _, swap in payload.items():
        swap["APY"] = (swap["oneDayVolume"] * feePercent * 0.01 * 365) / swap["TVL"]
    return 

def main():
    tokenPricesUSD = getTokenPricesUSD()
    swapsData = getGraphData()
    getOneDayVolume(tokenPricesUSD, swapsData)
    getSwapTLVs(tokenPricesUSD, swapsData)
    calculateAPYs()
    # Todo write to json file instead of logging
    for swapAddress, swap in payload.items():
        print("pool: {} volume: {} apy: {} tvl: {}".format(swapAddress, swap["oneDayVolume"], swap["APY"], swap["TVL"]))
    
if __name__ == "__main__":
    main()
            


    
