"""
fetch/sources/twse.py
台股資料：TWSE OpenAPI + FinMind。
已實測定案的流程：
  1. t187ap03_L → 公司代號、產業別代碼、已發行普通股數
  2. STOCK_DAY_ALL → Code、ClosingPrice、Change
  3. FinMind TaiwanStockInfo → stock_id、industry_category（中文）
  4. MI_INDEX → 各類股指數漲跌
  5. 市值 = ClosingPrice × 已發行股數
  6. 產業中文名優先 FinMind，fallback config.TW_INDUSTRY_CODE_MAP
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import urllib3
import requests

# Windows 環境 SSL 憑證可能有問題，suppress 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from fetch.config import (
    FINMIND_STOCK_INFO_URL,
    TWSE_COMPANY_URL,
    TWSE_MI_INDEX_URL,
    TWSE_STOCK_DAY_URL,
    TW_INDUSTRY_CODE_MAP,
    TW_MOVERS_MIN_MKTCAP,
    TW_MOVERS_MIN_TRADE_VALUE,
)

logger = logging.getLogger(__name__)

# HTTP 請求通用設定
_HEADERS = {"User-Agent": "Mozilla/5.0 twus-daily-bot/1.0"}
_TIMEOUT = 20


def _safe_float(val: Any) -> float | None:
    """轉 float，無效值回 None。"""
    try:
        import math
        f = float(str(val).replace(",", ""))
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────
# Step 1：TWSE t187ap03_L — 上市公司基本資料（含股數）
# ──────────────────────────────────────────────

def _fetch_company_info() -> dict[str, dict]:
    """
    回傳 {股票代號: {"name": str, "short_name": str, "industry_code": str, "shares": int}}。
    「已發行普通股數或TDR原股發行股數」欄位。
    TWSE 回傳 UTF-8，直接 decode('utf-8') 解析。
    """
    import json as _json
    resp = requests.get(TWSE_COMPANY_URL, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = _json.loads(resp.content.decode("utf-8"))

    result = {}
    for row in data:
        code = str(row.get("公司代號", "")).strip()
        if not code:
            continue
        industry_code = str(row.get("產業別", "")).strip()
        shares_raw = str(row.get("已發行普通股數或TDR原股發行股數", "0")).replace(",", "").strip()
        try:
            shares = int(float(shares_raw)) if shares_raw else 0
        except (ValueError, TypeError):
            shares = 0
        result[code] = {
            "name": str(row.get("公司簡稱", code)).strip(),  # 簡稱（如「台積電」）
            "full_name": str(row.get("公司名稱", "")).strip(),
            "industry_code": industry_code,
            "shares": shares,
        }
    return result


# ──────────────────────────────────────────────
# Step 2：TWSE STOCK_DAY_ALL — 全上市個股當日報價
# ──────────────────────────────────────────────

def _fetch_stock_day_all() -> dict[str, dict]:
    """
    回傳 {股票代號: {"price": float, "change": float, "change_pct": float, "name": str, "trade_value": float}}。
    STOCK_DAY_ALL 欄位（英文）：Code, Name, ClosingPrice, Change, TradeVolume, TradeValue...
    trade_value：成交金額（元），用於過濾低量股。
    """
    import json as _json
    resp = requests.get(TWSE_STOCK_DAY_URL, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    data = _json.loads(resp.content.decode("utf-8"))

    result = {}
    for row in data:
        code = str(row.get("Code", "")).strip()
        if not code:
            continue
        price = _safe_float(row.get("ClosingPrice"))
        name = str(row.get("Name", code)).strip()
        change_raw = row.get("Change", "")
        # Change 格式：'25.0000' / '-0.1400' / '0.0000'（已含符號）
        change = _safe_float(str(change_raw))
        if price is not None and change is not None:
            prev = price - change
            change_pct = round((change / prev) * 100, 4) if prev and prev != 0 else None
        else:
            change_pct = None
        # 成交金額（元）：TradeValue 欄位，含千分位逗號
        trade_value = _safe_float(str(row.get("TradeValue", "0")).replace(",", ""))
        result[code] = {
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "name": name,
            "trade_value": trade_value or 0.0,
        }
    return result


# ──────────────────────────────────────────────
# Step 3：FinMind TaiwanStockInfo — 產業中文名
# ──────────────────────────────────────────────

def _fetch_finmind_industry() -> dict[str, str]:
    """
    回傳 {stock_id: industry_category（中文）}。
    FinMind 無法取得時回空 dict（由呼叫方 fallback）。
    """
    try:
        resp = requests.get(FINMIND_STOCK_INFO_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        records = data.get("data", [])
        return {
            str(row.get("stock_id", "")).strip(): str(row.get("industry_category", "")).strip()
            for row in records
            if row.get("stock_id") and row.get("industry_category")
        }
    except Exception as e:
        logger.warning(f"FinMind TaiwanStockInfo 失敗: {e}")
        return {}


# ──────────────────────────────────────────────
# Step 4：TWSE MI_INDEX — 各類股指數漲跌
# ──────────────────────────────────────────────

def _fetch_mi_index() -> dict[str, float | None]:
    """
    回傳 {類股指數名稱: change_pct}。
    TWSE MI_INDEX API 實際欄位（繁中）：
      指數、收盤指數、漲跌、漲跌點數、漲跌百分比
    content 是 UTF-8 bytes，resp.encoding 可能被 requests 誤判，
    故直接 json.loads(resp.content.decode('utf-8'))。
    """
    import json as _json
    try:
        resp = requests.get(TWSE_MI_INDEX_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        # 直接用 utf-8 decode，避免 requests 根據 Content-Type 誤判
        data = _json.loads(resp.content.decode("utf-8"))

        result = {}
        for row in data:
            # 實際欄位名稱：指數、漲跌百分比
            name = str(row.get("指數", "")).strip()
            pct_raw = str(row.get("漲跌百分比", "")).strip()
            direction = str(row.get("漲跌", "")).strip()  # "+" 或 "-"
            if not name:
                continue
            pct = _safe_float(pct_raw)
            if pct is not None and direction == "-":
                pct = -abs(pct)
            result[name] = pct
        return result
    except Exception as e:
        logger.warning(f"MI_INDEX 取得失敗: {e}")
        return {}


# ──────────────────────────────────────────────
# 主要對外介面
# ──────────────────────────────────────────────

def fetch_tw_sectors(errors: list, top_n: int = 10) -> list[dict]:
    """
    組合 TWSE + FinMind，產出各產業板塊 + 市值前 top_n 個股。
    失敗時記 errors，不中斷。
    """
    # Step 1：公司基本資料（含股數）
    try:
        company_info = _fetch_company_info()
    except Exception as e:
        errors.append({"source": "TWSE:t187ap03_L", "stage": "sectors", "message": str(e)})
        company_info = {}

    # Step 2：當日報價
    try:
        stock_day = _fetch_stock_day_all()
    except Exception as e:
        errors.append({"source": "TWSE:STOCK_DAY_ALL", "stage": "sectors", "message": str(e)})
        stock_day = {}

    # Step 3：FinMind 產業中文名
    finmind_industry = _fetch_finmind_industry()
    if not finmind_industry:
        errors.append({
            "source": "FinMind:TaiwanStockInfo",
            "stage": "sectors",
            "message": "FinMind 取得失敗，改用 TW_INDUSTRY_CODE_MAP fallback",
        })

    # Step 4：MI_INDEX 類股指數漲跌
    mi_index = _fetch_mi_index()
    if not mi_index:
        errors.append({
            "source": "TWSE:MI_INDEX",
            "stage": "sectors",
            "message": "MI_INDEX 取得失敗，板塊漲跌改用成分股市值加權平均",
        })

    # ── 建個股資料表 ──
    # {stock_code: {"name": str, "industry": str, "mktcap": float, "change_pct": float}}
    stock_table: dict[str, dict] = {}
    for code, comp in company_info.items():
        price_data = stock_day.get(code, {})
        price = price_data.get("price")
        shares = comp.get("shares", 0)
        mktcap = price * shares if price is not None and shares > 0 else None

        # 產業中文名：優先 FinMind，fallback config
        industry_code = comp.get("industry_code", "")
        industry = (
            finmind_industry.get(code)
            or TW_INDUSTRY_CODE_MAP.get(industry_code, industry_code)
        )

        # 公司名稱：優先 STOCK_DAY_ALL 的 Name，fallback t187ap03_L 的公司簡稱
        name = (
            price_data.get("name")
            or comp.get("name", code)
        )

        stock_table[code] = {
            "symbol": f"{code}.TW",
            "name": name,
            "industry": industry,
            "mktcap": mktcap,
            "change_pct": price_data.get("change_pct"),
        }

    # ── 按產業分組 ──
    industry_groups: dict[str, list[dict]] = defaultdict(list)
    for code, info in stock_table.items():
        ind = info["industry"]
        if ind and info["mktcap"] is not None:
            industry_groups[ind].append(info)

    # ── 組板塊結果 ──
    sectors = []
    for industry, stocks in industry_groups.items():
        # 板塊漲跌：優先 MI_INDEX
        sector_change_pct = None
        # 嘗試對應 MI_INDEX 名稱（模糊匹配：industry 名稱包含在 index 名稱內）
        for idx_name, idx_change in mi_index.items():
            if industry.replace("業", "") in idx_name or idx_name.replace("類指數", "") in industry:
                sector_change_pct = idx_change
                break

        # fallback：成分股市值加權平均
        if sector_change_pct is None:
            valid = [(s["mktcap"], s["change_pct"]) for s in stocks
                     if s["mktcap"] and s["change_pct"] is not None]
            if valid:
                total_mktcap = sum(m for m, _ in valid)
                if total_mktcap > 0:
                    sector_change_pct = round(
                        sum(m * c for m, c in valid) / total_mktcap, 4
                    )

        # 市值前 top_n 個股
        sorted_stocks = sorted(stocks, key=lambda s: s["mktcap"] or 0, reverse=True)
        constituents = [
            {
                "symbol": s["symbol"],
                "name": s["name"],
                "weight_pct": None,  # 無 ETF 權重，只有市值排名
                "mktcap": s["mktcap"],
                "change_pct": s["change_pct"],
            }
            for s in sorted_stocks[:top_n]
        ]

        sectors.append({
            "sector": industry,
            "index": f"TWSE {industry}類指數",  # 參考名稱
            "change_pct": sector_change_pct,
            "constituents": constituents,
        })

    # 按板塊市值加總排序（大產業先）
    sectors.sort(
        key=lambda s: sum(c["mktcap"] or 0 for c in s["constituents"]),
        reverse=True,
    )

    return sectors


def fetch_twii_quote(errors: list) -> dict | None:
    """
    從 STOCK_DAY_ALL 取加權指數代理（TWII 本身不在個股清單）。
    加權指數數值從 yfinance 來（已在 yf.py 抓），這裡提供備援。
    """
    # 加權指數不在 STOCK_DAY_ALL，此函數為預留接口
    # 實際加權指數從 yf.py fetch_indices() 取
    return None


def fetch_tw_movers(
    errors: list,
    top_n: int = 10,
    min_mktcap: float = TW_MOVERS_MIN_MKTCAP,
    min_trade_value: float = TW_MOVERS_MIN_TRADE_VALUE,
) -> tuple[list[dict], list[dict]]:
    """
    從 STOCK_DAY_ALL 掃全上市，找當日漲跌幅最大的個股。

    過濾條件（雙重門檻，AND 關係）：
    - min_mktcap：市值下限（預設 30 億），過濾微型股
    - min_trade_value：成交金額下限（預設 5000 萬元），過濾無量股

    每個 mover 帶 name（中文股名）+ sector（所屬產業），由 company_info + FinMind 提供。
    回傳 (top_gainers, top_losers)。
    """
    try:
        company_info = _fetch_company_info()
    except Exception as e:
        errors.append({"source": "TWSE:t187ap03_L", "stage": "highlights", "message": str(e)})
        company_info = {}

    try:
        stock_day = _fetch_stock_day_all()
    except Exception as e:
        errors.append({"source": "TWSE:STOCK_DAY_ALL", "stage": "highlights", "message": str(e)})
        return [], []

    # FinMind 產業中文名（補產業欄位用）
    finmind_industry = _fetch_finmind_industry()

    movers = []
    for code, price_data in stock_day.items():
        price = price_data.get("price")
        change_pct = price_data.get("change_pct")
        if price is None or change_pct is None:
            continue

        # 市值過濾
        comp = company_info.get(code, {})
        shares = comp.get("shares", 0)
        mktcap = price * shares if shares > 0 else 0
        if mktcap < min_mktcap:
            continue

        # 成交額過濾（STOCK_DAY_ALL 的 TradeValue 欄位）
        trade_value = price_data.get("trade_value", 0) or 0
        if trade_value < min_trade_value:
            continue

        # 股名：優先 STOCK_DAY_ALL 的 Name，fallback t187ap03_L 的公司簡稱
        name = price_data.get("name") or comp.get("name", code)

        # 產業：優先 FinMind industry_category，fallback TW_INDUSTRY_CODE_MAP
        industry_code = comp.get("industry_code", "")
        sector = (
            finmind_industry.get(code)
            or TW_INDUSTRY_CODE_MAP.get(industry_code, "")
        )

        movers.append({
            "symbol": f"{code}.TW",
            "name": name,
            "sector": sector,
            "region": "TW",
            "change_pct": change_pct,
            "mktcap": mktcap,
            "trade_value": trade_value,
            "note": "",
        })

    movers.sort(key=lambda x: x["change_pct"], reverse=True)

    def _to_mover(m: dict) -> dict:
        """只保留 schema 需要的欄位。"""
        out: dict = {
            "symbol": m["symbol"],
            "name": m["name"],
            "region": m["region"],
            "change_pct": m["change_pct"],
            "note": m["note"],
        }
        if m.get("sector"):
            out["sector"] = m["sector"]
        return out

    gainers = [_to_mover(m) for m in movers[:top_n]]
    losers  = [_to_mover(m) for m in movers[-top_n:][::-1]]
    return gainers, losers
