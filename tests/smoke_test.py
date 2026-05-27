import ccxt
import pandas
import ta
import redis
import sqlalchemy
import pydantic
import loguru

print("Core imports OK")

ex = ccxt.blofin({"options": {"defaultType": "swap"}})
ticker = ex.fetch_ticker("BTC/USDT:USDT")
print(f"Blofin BTC price: {ticker['last']}")
print("Blofin API connectivity OK")
