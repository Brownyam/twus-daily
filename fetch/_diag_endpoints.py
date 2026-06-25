"""
_diag_endpoints.py — 一次性診斷：從 GHA runner（Azure IP）測各候選台股端點。
目的：確認哪些 host 從 GitHub Actions 抓得到（openapi.twse vs www.twse vs FinMind）。
跑完即可刪。
"""
from __future__ import annotations

import requests

H = {"User-Agent": "Mozilla/5.0 twus-daily-bot/1.0"}
T = 25

CANDIDATES = [
    # (label, url)
    ("openapi STOCK_DAY_ALL", "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"),
    ("www  STOCK_DAY_ALL json", "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json"),
    ("www  STOCK_DAY_ALL rwd",  "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"),
    ("openapi t187ap03_L",      "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"),
    ("www  opendata t187ap03_L","https://www.twse.com.tw/opendata/t187ap03_L"),
    ("www  MI_INDEX",           "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALL"),
    ("www  rwd MI_INDEX",       "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALL"),
    ("FinMind TaiwanStockInfo", "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"),
]


def probe(label: str, url: str) -> None:
    try:
        r = requests.get(url, headers=H, timeout=T)
        body = r.content.decode("utf-8", "replace")
        head = body[:100].replace("\n", " ")
        print(f"[{label:26}] HTTP {r.status_code} | len={len(body):>8} | ct={r.headers.get('content-type','?')[:30]}")
        print(f"    head: {head!r}")
    except Exception as e:
        print(f"[{label:26}] EXC {type(e).__name__}: {e}")


if __name__ == "__main__":
    for label, url in CANDIDATES:
        probe(label, url)
        # 失敗的話再試一次，看是不是 transient
        # （只對前 5 個 TWSE 端點重試）
