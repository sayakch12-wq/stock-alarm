"""야후 파이낸스에서 최근 5년 일봉을 받아 data/<티커>.csv로 저장 (GitHub Actions에서 실행)"""
import csv, os, sys, time
from datetime import datetime, timezone

import requests

import backtest as bt


def fetch(ticker: str) -> int:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5y&events=div,splits"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    d = r.json()["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    adj = d["indicators"].get("adjclose", [{}])[0].get("adjclose")
    os.makedirs(bt.DATA_DIR, exist_ok=True)
    n = 0
    with open(os.path.join(bt.DATA_DIR, f"{ticker}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        for i, ts in enumerate(d["timestamp"]):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c):
                continue
            k = (adj[i] / c) if adj and adj[i] else 1.0  # 배당·분할 보정 비율
            day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            w.writerow([day, round(o * k, 4), round(h * k, 4), round(l * k, 4), round(c * k, 4), int(q["volume"][i] or 0)])
            n += 1
    return n


if __name__ == "__main__":
    failed = []
    for tk in bt.TICKERS:
        try:
            print(tk, fetch(tk), "rows")
        except Exception as e:  # noqa: BLE001
            print(tk, "실패:", e)
            failed.append(tk)
        time.sleep(1)
    if failed:
        sys.exit(f"데이터 받기 실패: {failed}")
