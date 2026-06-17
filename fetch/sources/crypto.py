"""
fetch/sources/crypto.py
加密貨幣：BTC / ETH。
優先 CoinGecko free API，失敗 fallback yfinance BTC-USD / ETH-USD。
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from fetch.config import (
    COINGECKO_PRICE_URL,
    CRYPTO_COINGECKO,
    CRYPTO_YF_FALLBACK,
)

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 twus-daily-bot/1.0"}
_TIMEOUT = 15


def _safe_float(val: Any) -> float | None:
    try:
        import math
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _fetch_coingecko() -> dict[str, dict] | None:
    """
    從 CoinGecko simple/price 取 BTC/ETH 價格與 24h 漲跌幅。
    回傳 {"BTC": {"price": x, "change_pct_24h": y}, ...}，失敗回 None。
    """
    try:
        resp = requests.get(COINGECKO_PRICE_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        result = {}
        for cg_id, symbol in CRYPTO_COINGECKO.items():
            info = data.get(cg_id, {})
            price = _safe_float(info.get("usd"))
            change_pct_24h = _safe_float(info.get("usd_24h_change"))
            if change_pct_24h is not None:
                change_pct_24h = round(change_pct_24h, 4)
            result[symbol] = {"price": price, "change_pct_24h": change_pct_24h}
        return result if result else None
    except Exception as e:
        logger.warning(f"CoinGecko 失敗: {e}")
        return None


def _fetch_yf_fallback() -> dict[str, dict]:
    """
    yfinance fallback：抓 BTC-USD / ETH-USD。
    """
    import yfinance as yf

    result = {}
    for symbol, yf_ticker in CRYPTO_YF_FALLBACK.items():
        try:
            t = yf.Ticker(yf_ticker)
            fi = t.fast_info
            price = _safe_float(getattr(fi, "last_price", None))
            prev = _safe_float(getattr(fi, "previous_close", None))
            if price is not None and prev is not None and prev != 0:
                change_pct_24h = round((price - prev) / prev * 100, 4)
            else:
                change_pct_24h = None
            result[symbol] = {"price": price, "change_pct_24h": change_pct_24h}
        except Exception as e:
            logger.warning(f"yfinance crypto fallback 失敗 {yf_ticker}: {e}")
            result[symbol] = {"price": None, "change_pct_24h": None}
    return result


def fetch_crypto(errors: list) -> list[dict]:
    """
    主要對外介面。
    回傳 [{"symbol": "BTC", "price": x, "change_pct_24h": y}, ...]。
    """
    data = _fetch_coingecko()
    if data is None:
        errors.append({
            "source": "CoinGecko",
            "stage": "crypto",
            "message": "CoinGecko API 失敗，使用 yfinance fallback",
        })
        data = _fetch_yf_fallback()

    result = []
    for symbol in ["BTC", "ETH"]:
        info = data.get(symbol, {})
        result.append({
            "symbol": symbol,
            "price": info.get("price"),
            "change_pct_24h": info.get("change_pct_24h"),
        })
    return result
