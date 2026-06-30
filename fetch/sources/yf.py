"""
fetch/sources/yf.py
yfinance 資料抓取：指數、Macro、美股板塊 ETF + holdings、期貨。
任何單一 ticker 失敗 → 返回 null 數值 + 記 errors[]，不中斷。
"""

from __future__ import annotations

import logging
import time
from typing import Any

import yfinance as yf

from fetch.config import (
    FUTURES,
    INDICES_T1,
    INDICES_T2,
    MACRO_SYMBOLS,
    SSGA_HOLDINGS_URL,
    ISHARES_SOXX_URL,
    US_SECTOR_ETFS,
    US_SECTOR_TOP_N,
)

# ETF holdings fallback 只對以下發行商有效；其餘靜默跳過（避免噴 errors）
_SSGA_ETFS = frozenset({"XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","XLB","XLC","XLRE"})
_ISHARES_ETFS = frozenset({"SOXX"})

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 通用工具
# ──────────────────────────────────────────────

def _safe_float(val: Any) -> float | None:
    """把任意值轉 float；無效值回傳 None（不用 NaN）。"""
    try:
        f = float(val)
        import math
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _fetch_ticker_info(symbol: str) -> dict[str, Any]:
    """
    取單一 ticker 的 fast_info（price / prev_close / change）。
    回傳 dict；失敗回 empty dict。
    """
    try:
        t = yf.Ticker(symbol)
        fi = t.fast_info
        price = _safe_float(getattr(fi, "last_price", None))
        prev_close = _safe_float(getattr(fi, "previous_close", None))
        if price is not None and prev_close is not None and prev_close != 0:
            change = price - prev_close
            change_pct = round((change / prev_close) * 100, 4)
        else:
            change = None
            change_pct = None
        return {
            "price": price,
            "prev_close": prev_close,
            "change": _safe_float(change),
            "change_pct": change_pct,
        }
    except Exception as e:
        logger.warning(f"yf fast_info 失敗 {symbol}: {e}")
        return {}


# ──────────────────────────────────────────────
# 指數
# ──────────────────────────────────────────────

def fetch_indices(errors: list) -> list[dict]:
    """
    抓 T1 + T2 指數。單一 ticker 失敗不中斷，記進 errors。
    """
    result = []
    for meta in INDICES_T1 + INDICES_T2:
        sym = meta["symbol"]
        info = _fetch_ticker_info(sym)
        if not info:
            errors.append({
                "source": f"yf:{sym}",
                "stage": "indices",
                "message": f"無法取得 {sym} 報價",
            })
        result.append({
            "symbol": sym,
            "name": meta["name"],
            "region": meta["region"],
            "price": info.get("price"),
            "change": info.get("change"),
            "change_pct": info.get("change_pct"),
            "prev_close": info.get("prev_close"),
        })
    return result


# ──────────────────────────────────────────────
# Macro
# ──────────────────────────────────────────────

def fetch_macro(errors: list) -> dict:
    """
    抓 VIX、US10Y、US30Y、DXY、期貨。
    殖利率 change 單位為 bps = (今-昨)*100。
    """
    macro: dict[str, Any] = {"futures": []}

    # VIX
    vix_sym = MACRO_SYMBOLS["vix"]
    vix_info = _fetch_ticker_info(vix_sym)
    if vix_info:
        macro["vix"] = {
            "symbol": vix_sym,
            "value": vix_info.get("price"),
            "change_pct": vix_info.get("change_pct"),
        }
    else:
        macro["vix"] = None
        errors.append({"source": f"yf:{vix_sym}", "stage": "macro", "message": "VIX 取得失敗"})

    # 殖利率：^TNX ^TYX — fast_info 回傳的 last_price 是殖利率%（如 4.25）
    for key, sym in [("us10y", MACRO_SYMBOLS["us10y"]), ("us30y", MACRO_SYMBOLS["us30y"])]:
        info = _fetch_ticker_info(sym)
        if info and info.get("price") is not None:
            value = info["price"]
            prev = info.get("prev_close")
            change_bps = round((value - prev) * 100, 2) if prev is not None else None
            macro[key] = {"symbol": sym, "value": value, "change_bps": change_bps}
        else:
            macro[key] = None
            errors.append({"source": f"yf:{sym}", "stage": "macro", "message": f"{key} 殖利率取得失敗"})

    # DXY
    dxy_sym = MACRO_SYMBOLS["dxy"]
    dxy_info = _fetch_ticker_info(dxy_sym)
    if dxy_info:
        macro["dxy"] = {
            "symbol": dxy_sym,
            "value": dxy_info.get("price"),
            "change_pct": dxy_info.get("change_pct"),
        }
    else:
        macro["dxy"] = None
        errors.append({"source": f"yf:{dxy_sym}", "stage": "macro", "message": "DXY 取得失敗"})

    # 期貨
    for fut in FUTURES:
        info = _fetch_ticker_info(fut["symbol"])
        macro["futures"].append({
            "symbol": fut["symbol"],
            "name": fut["name"],
            "change_pct": info.get("change_pct") if info else None,
        })
        if not info:
            errors.append({
                "source": f"yf:{fut['symbol']}",
                "stage": "macro",
                "message": f"期貨 {fut['symbol']} 取得失敗",
            })

    return macro


# ──────────────────────────────────────────────
# 美股板塊 ETF + holdings
# ──────────────────────────────────────────────

def _fetch_holdings_from_funds_data(etf: str) -> list[dict] | None:
    """
    優先來源：yfinance Ticker.funds_data.top_holdings。
    失敗或無資料回 None。
    """
    try:
        t = yf.Ticker(etf)
        fd = t.funds_data
        if fd is None:
            return None
        holdings = fd.top_holdings  # DataFrame: index=symbol, columns=[holdingName, holdingPercent, ...]
        if holdings is None or holdings.empty:
            return None

        result = []
        for symbol, row in holdings.head(US_SECTOR_TOP_N).iterrows():
            name = str(row.get("holdingName", symbol))
            weight_pct = _safe_float(row.get("holdingPercent"))
            if weight_pct is not None:
                weight_pct = round(weight_pct * 100, 2)  # 轉百分比

            # 個股報價
            stock_info = _fetch_ticker_info(str(symbol))
            result.append({
                "symbol": str(symbol),
                "name": name,
                "weight_pct": weight_pct,
                "price": stock_info.get("price") if stock_info else None,
                "mktcap": None,  # funds_data 沒提供，留 null
                "change_pct": stock_info.get("change_pct") if stock_info else None,
            })
        return result if result else None
    except Exception as e:
        logger.warning(f"funds_data.top_holdings 失敗 {etf}: {e}")
        return None


def _fetch_holdings_fallback(etf: str, errors: list) -> list[dict]:
    """
    Fallback：從 ETF 發行商抓 holdings xlsx/csv。
    XL*（SSGA）和 SOXX（iShares）有已知 URL；其餘靜默回空 list，不記 errors。
    """
    import io
    import requests
    import pandas as pd

    etf_u = etf.upper()
    if etf_u not in _SSGA_ETFS and etf_u not in _ISHARES_ETFS:
        logger.info(f"{etf} 無 fallback holdings URL，跳過")
        return []

    is_soxx = (etf_u == "SOXX")

    try:
        if is_soxx:
            url = ISHARES_SOXX_URL
            headers = {"User-Agent": "Mozilla/5.0 twus-daily-bot/1.0"}
            resp = requests.get(url, timeout=20, headers=headers)
            resp.raise_for_status()
            # iShares CSV 前幾行是 metadata，先 skip 到 header
            lines = resp.text.splitlines()
            # 找 header 行（包含 "Ticker" 或 "Name"）
            start = 0
            for i, line in enumerate(lines):
                if "Ticker" in line and "Name" in line:
                    start = i
                    break
            df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
            # 取前 N 非空 ticker
            tickers = df["Ticker"].dropna().str.strip()
            tickers = [t for t in tickers if t and t != "-"][:US_SECTOR_TOP_N]
        else:
            url = SSGA_HOLDINGS_URL.format(etf_lower=etf.lower())
            headers = {"User-Agent": "Mozilla/5.0 twus-daily-bot/1.0"}
            resp = requests.get(url, timeout=20, headers=headers)
            resp.raise_for_status()
            # SSGA xlsx：第一張 sheet，略過前幾行元資料
            df = pd.read_excel(io.BytesIO(resp.content), header=None)
            # 找 "Ticker" 欄位的行號
            header_row = None
            for i, row in df.iterrows():
                if any("Ticker" in str(c) for c in row):
                    header_row = i
                    break
            if header_row is None:
                raise ValueError("找不到 Ticker 欄位")
            df = pd.read_excel(io.BytesIO(resp.content), header=header_row)
            tickers = df["Ticker"].dropna().str.strip()
            tickers = [t for t in tickers if t and t != "-"][:US_SECTOR_TOP_N]

        result = []
        for sym in tickers:
            stock_info = _fetch_ticker_info(sym)
            result.append({
                "symbol": sym,
                "name": sym,
                "weight_pct": None,
                "price": stock_info.get("price") if stock_info else None,
                "mktcap": None,
                "change_pct": stock_info.get("change_pct") if stock_info else None,
            })
        return result

    except Exception as e:
        errors.append({
            "source": f"holdings_fallback:{etf}",
            "stage": "sectors",
            "message": f"ETF holdings fallback 失敗 {etf}: {e}",
        })
        return []


def fetch_us_sectors(errors: list) -> list[dict]:
    """
    抓美股板塊 ETF 的 change_pct + holdings。

    holdings 抓取順序：
    - SSGA（XL*）/iShares（SOXX）有完整 holdings 清單來源 → 優先走發行商 xlsx/csv，
      可取真正前 US_SECTOR_TOP_N 檔；yfinance funds_data.top_holdings 受 Yahoo API
      限制固定只回 top 10，不受 head(N) 影響，故不適合當這些 ETF 的主來源。
    - 其餘 ETF（ARKK/IBB/ITA/KWEB/ICLN 等無已知發行商端點）走 funds_data，
      上限即 Yahoo 給的 10 檔。
    - 兩條路都失敗，才記一次 errors，回空 constituents。
    """
    result = []
    for meta in US_SECTOR_ETFS:
        etf = meta["etf"]
        sector = meta["sector"]
        etf_u = etf.upper()
        has_full_list_source = etf_u in _SSGA_ETFS or etf_u in _ISHARES_ETFS

        # ETF 本身漲跌
        etf_info = _fetch_ticker_info(etf)
        if not etf_info:
            errors.append({
                "source": f"yf:{etf}",
                "stage": "sectors",
                "message": f"ETF {etf} 報價取得失敗",
            })

        change_pct = etf_info.get("change_pct") if etf_info else None

        # Holdings
        constituents = None
        if has_full_list_source:
            constituents = _fetch_holdings_fallback(etf, [])  # 安靜試，失敗不記 errors（還有 funds_data 可補）
        if not constituents:
            constituents = _fetch_holdings_from_funds_data(etf)
        if not constituents:
            errors.append({
                "source": f"holdings:{etf}",
                "stage": "sectors",
                "message": f"ETF {etf} holdings 取得失敗（fallback + funds_data 皆失敗）",
            })
            constituents = []

        result.append({
            "sector": sector,
            "etf": etf,
            "change_pct": change_pct,
            "constituents": constituents,
        })

    return result
