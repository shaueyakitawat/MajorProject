import yfinance as yf

data = yf.download("^NSEI", period="5d")
print(data.tail())