from fastapi import FastAPI
import yfinance as yf

app = FastAPI()

@app.get("/")
def root():
    return {"status": "running"}

@app.get("/nifty")
def get_nifty_data():
    data = yf.download("^NSEI", period="5d")

    # 🔧 Flatten columns (fix MultiIndex problem)
    data.columns = [col[0] if isinstance(col, tuple) else col for col in data.columns]

    # Convert index to string for JSON
    data.reset_index(inplace=True)
    data["Date"] = data["Date"].astype(str)

    return data.tail().to_dict(orient="records")