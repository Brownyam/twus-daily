"""
fetch/sources/twse.py
台股資料：www.twse.com.tw（主）+ FinMind（產業）。

⚠️ 來源策略（2026-06-25 改）：
  openapi.twse.com.tw 會對 GitHub Actions 的共享雲端 IP 間歇性節流，回 HTML
  封鎖頁（「因為您的連線數過多」），json.loads 就報 "Expecting value: line 1
  column 1 (char 0)"。實測 www.twse.com.tw（同資料、不同基礎設施）在 GHA 穩定，
  故主來源全改 www，openapi 僅作 fallback。

資料流（全部走 GHA 實測穩定來源）：
  1. STOCK_DAY_ALL (www, CSV) → 代號、股名、收盤、漲跌、成交金額
  2. MI_QFIIS     (www, JSON) → 發行股數（算市值）
  3. FinMind TaiwanStockInfo  → 產業中文名
  4. MI_INDEX     (www, JSON tables) → 各類股指數漲跌（選配，有市值加權 fallback）
  市值 = 收盤價 × 發行股數
"""

from __future__ import annotations

import csv
import io
import json as _json
import logging
import math
import time
from collections import defaultdict
from typing import Any

import requests
import urllib3

# Windows 環境 SSL 憑證可能有問題，suppress 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from fetch.config import (
    FINMIND_STOCK_INFO_URL,
    TWSE_COMPANY_URL,
    TWSE_MI_INDEX_OPENAPI_URL,
    TWSE_MI_INDEX_WWW_URL,
    TWSE_QFIIS_URL,
    TWSE_STOCK_DAY_CSV_URL,
    TWSE_STOCK_DAY_OPENAPI_URL,
    TW_MOVERS_MIN_MKTCAP,
    TW_MOVERS_MIN_TRADE_VALUE,
)

logger = logging.getLogger(__name__)

# HTTP 請求通用設定
_HEADERS = {"User-Agent": "Mozilla/5.0 twus-daily-bot/1.0"}
_TIMEOUT = 25
_RETRIES = 3
_BACKOFF = 1.5  # 秒，retry 間隔（遞增）


def _safe_float(val: Any) -> float | None:
    """轉 float，無效值回 None。"""
    try:
        f = float(str(val).replace(",", "").strip())
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _looks_blocked(text: str) -> bool:
    """偵測 TWSE 節流／HTML 封鎖頁（非 JSON/CSV 資料）。"""
    head = text.lstrip()[:200]
    if not head:
        return True  # 空 body
    if head[0] == "<":  # HTML
        return True
    if "因為您的連線" in head or "連線數過多" in head:
        return True
    return False


def _get(url: str, expect: str = "json") -> str:
    """
    GET 帶 retry + 封鎖頁偵測。回傳 response.text（utf-8）。
    expect: "json" 或 "csv"，只影響錯誤訊息。封鎖／空 body 視為失敗會 retry。
    全部 retry 用盡才 raise。
    """
    last_exc: Exception | None = None
    for attempt in range(1, _RETRIES + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            text = resp.content.decode("utf-8", "replace")
            if _looks_blocked(text):
                raise ValueError(f"疑似節流/封鎖頁（{len(text)} bytes）")
            return text
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if attempt < _RETRIES:
                time.sleep(_BACKOFF * attempt)
    raise last_exc  # type: ignore[misc]


# ──────────────────────────────────────────────
# Step 1：STOCK_DAY_ALL — 全上市個股當日報價（www CSV，openapi JSON 備援）
# ──────────────────────────────────────────────

# www CSV 欄位（0-based）
_CSV_CODE, _CSV_NAME = 1, 2
_CSV_TRADEVAL = 4
_CSV_CLOSE, _CSV_CHANGE = 8, 9


def _parse_stock_day_csv(text: str) -> dict[str, dict]:
    """解析 www STOCK_DAY_ALL CSV。漲跌價差欄已含正負號。"""
    result: dict[str, dict] = {}
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if len(row) <= _CSV_CHANGE:
            continue
        code = row[_CSV_CODE].strip()
        # 跳過表頭與非資料列（代號非英數）
        if not code or not code[0].isalnum() or code in ("證券代號",):
            continue
        price = _safe_float(row[_CSV_CLOSE])
        change = _safe_float(row[_CSV_CHANGE])  # 已含符號
        if price is None:
            continue
        if change is not None and price - change not in (0, None):
            prev = price - change
            change_pct = round((change / prev) * 100, 4) if prev else None
        else:
            change_pct = None
        result[code] = {
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "name": row[_CSV_NAME].strip() or code,
            "trade_value": _safe_float(row[_CSV_TRADEVAL]) or 0.0,
        }
    return result


def _parse_stock_day_openapi(text: str) -> dict[str, dict]:
    """解析 openapi STOCK_DAY_ALL JSON（備援用，欄位英文）。"""
    data = _json.loads(text)
    result: dict[str, dict] = {}
    for row in data:
        code = str(row.get("Code", "")).strip()
        if not code:
            continue
        price = _safe_float(row.get("ClosingPrice"))
        change = _safe_float(row.get("Change"))
        if price is None:
            continue
        if change is not None and price - change != 0:
            change_pct = round((change / (price - change)) * 100, 4)
        else:
            change_pct = None
        result[code] = {
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "name": str(row.get("Name", code)).strip() or code,
            "trade_value": _safe_float(str(row.get("TradeValue", "0"))) or 0.0,
        }
    return result


def _fetch_stock_day_all() -> dict[str, dict]:
    """www CSV 主、openapi JSON 備援。回 {code: {price, change, change_pct, name, trade_value}}。"""
    try:
        return _parse_stock_day_csv(_get(TWSE_STOCK_DAY_CSV_URL, "csv"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"STOCK_DAY_ALL www 失敗，改試 openapi: {e}")
        return _parse_stock_day_openapi(_get(TWSE_STOCK_DAY_OPENAPI_URL, "json"))


# ──────────────────────────────────────────────
# Step 2：MI_QFIIS — 發行股數（www；t187ap03_L 為 local 備援）
# ──────────────────────────────────────────────

def _fetch_company_shares() -> dict[str, int]:
    """回 {證券代號: 發行股數}。主來源 MI_QFIIS（www），失敗 fallback t187ap03_L（openapi）。"""
    try:
        data = _json.loads(_get(TWSE_QFIIS_URL, "json"))
        rows = data.get("data", []) if isinstance(data, dict) else []
        result: dict[str, int] = {}
        for row in rows:
            # 欄位：[證券代號, 證券名稱, ISIN, 發行股數, ...]
            if not row or len(row) < 4:
                continue
            code = str(row[0]).strip()
            shares = _safe_float(row[3])
            if code and shares and shares > 0:
                result[code] = int(shares)
        if result:
            return result
        raise ValueError("MI_QFIIS 無資料列")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"MI_QFIIS 失敗，改試 t187ap03_L: {e}")
        # fallback：openapi t187ap03_L（已發行普通股數）— 間歇性可用
        data = _json.loads(_get(TWSE_COMPANY_URL, "json"))
        result = {}
        for row in data:
            code = str(row.get("公司代號", "")).strip()
            raw = str(row.get("已發行普通股數或TDR原股發行股數", "0")).replace(",", "").strip()
            try:
                shares = int(float(raw)) if raw else 0
            except (ValueError, TypeError):
                shares = 0
            if code and shares > 0:
                result[code] = shares
        return result


# ──────────────────────────────────────────────
# Step 3：FinMind TaiwanStockInfo — 產業中文名
# ──────────────────────────────────────────────

def _fetch_finmind_industry() -> dict[str, str]:
    """回 {stock_id: industry_category（中文）}。取不到回空 dict（呼叫方 fallback）。"""
    try:
        resp = requests.get(FINMIND_STOCK_INFO_URL, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        records = resp.json().get("data", [])
        return {
            str(r.get("stock_id", "")).strip(): str(r.get("industry_category", "")).strip()
            for r in records
            if r.get("stock_id") and r.get("industry_category")
        }
    except Exception as e:  # noqa: BLE001
        logger.warning(f"FinMind TaiwanStockInfo 失敗: {e}")
        return {}


# ──────────────────────────────────────────────
# Step 4：MI_INDEX — 各類股指數漲跌（www tables 主，openapi flat 備援）
# ──────────────────────────────────────────────

def _fetch_mi_index() -> dict[str, float | None]:
    """回 {類股指數名稱: change_pct}。"""
    # 主來源：www tables 結構
    try:
        data = _json.loads(_get(TWSE_MI_INDEX_WWW_URL, "json"))
        result: dict[str, float | None] = {}
        for table in data.get("tables", []):
            fields = table.get("fields", [])
            # 只取「價格指數」表（fields[0]=='指數'），排除「報酬指數」表
            if not fields or str(fields[0]).strip() != "指數":
                continue
            pct_i = next(
                (i for i, f in enumerate(fields) if "漲跌百分比" in str(f)), None
            )
            if pct_i is None:
                continue
            for row in table.get("data", []):
                if len(row) <= pct_i:
                    continue
                name = str(row[0]).strip()
                pct = _safe_float(row[pct_i])  # 已含符號
                if name:
                    result[name] = pct
        if result:
            return result
        raise ValueError("MI_INDEX www 無類股指數列")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"MI_INDEX www 失敗，改試 openapi: {e}")
        # fallback：openapi flat 陣列
        try:
            data = _json.loads(_get(TWSE_MI_INDEX_OPENAPI_URL, "json"))
            result = {}
            for row in data:
                name = str(row.get("指數", "")).strip()
                pct = _safe_float(str(row.get("漲跌百分比", "")))
                direction = str(row.get("漲跌", "")).strip()
                if pct is not None and direction == "-":
                    pct = -abs(pct)
                if name:
                    result[name] = pct
            return result
        except Exception as e2:  # noqa: BLE001
            logger.warning(f"MI_INDEX openapi 也失敗: {e2}")
            return {}


# ──────────────────────────────────────────────
# 主要對外介面（簽名不變）
# ──────────────────────────────────────────────

def fetch_tw_sectors(errors: list, top_n: int = 10) -> list[dict]:
    """組合 TWSE + FinMind，產出各產業板塊 + 市值前 top_n 個股。失敗記 errors 不中斷。"""
    # 報價（含股名、量能）
    try:
        stock_day = _fetch_stock_day_all()
    except Exception as e:
        errors.append({"source": "TWSE:STOCK_DAY_ALL", "stage": "sectors", "message": str(e)})
        stock_day = {}

    # 發行股數（算市值）
    try:
        shares_map = _fetch_company_shares()
    except Exception as e:
        errors.append({"source": "TWSE:MI_QFIIS", "stage": "sectors", "message": str(e)})
        shares_map = {}

    # 產業中文名
    finmind_industry = _fetch_finmind_industry()
    if not finmind_industry:
        errors.append({
            "source": "FinMind:TaiwanStockInfo",
            "stage": "sectors",
            "message": "FinMind 取得失敗，產業分類缺失",
        })

    # 類股指數漲跌（選配）
    mi_index = _fetch_mi_index()
    if not mi_index:
        errors.append({
            "source": "TWSE:MI_INDEX",
            "stage": "sectors",
            "message": "MI_INDEX 取得失敗，板塊漲跌改用成分股市值加權平均",
        })

    # ── 建個股資料表（以報價 universe 為主）──
    stock_table: dict[str, dict] = {}
    for code, price_data in stock_day.items():
        price = price_data.get("price")
        shares = shares_map.get(code, 0)
        mktcap = price * shares if price is not None and shares > 0 else None
        industry = finmind_industry.get(code, "")
        stock_table[code] = {
            "symbol": f"{code}.TW",
            "name": price_data.get("name") or code,
            "industry": industry,
            "mktcap": mktcap,
            "change_pct": price_data.get("change_pct"),
        }

    # ── 按產業分組 ──
    industry_groups: dict[str, list[dict]] = defaultdict(list)
    for info in stock_table.values():
        ind = info["industry"]
        if ind and info["mktcap"] is not None:
            industry_groups[ind].append(info)

    # ── 組板塊結果 ──
    sectors = []
    for industry, stocks in industry_groups.items():
        # 板塊漲跌：優先 MI_INDEX 模糊匹配
        sector_change_pct = None
        for idx_name, idx_change in mi_index.items():
            if industry.replace("業", "") in idx_name or idx_name.replace("類指數", "") in industry:
                sector_change_pct = idx_change
                break
        # fallback：成分股市值加權平均
        if sector_change_pct is None:
            valid = [(s["mktcap"], s["change_pct"]) for s in stocks
                     if s["mktcap"] and s["change_pct"] is not None]
            if valid:
                total = sum(m for m, _ in valid)
                if total > 0:
                    sector_change_pct = round(sum(m * c for m, c in valid) / total, 4)

        sorted_stocks = sorted(stocks, key=lambda s: s["mktcap"] or 0, reverse=True)
        constituents = [
            {
                "symbol": s["symbol"],
                "name": s["name"],
                "weight_pct": None,
                "mktcap": s["mktcap"],
                "change_pct": s["change_pct"],
            }
            for s in sorted_stocks[:top_n]
        ]
        sectors.append({
            "sector": industry,
            "index": f"TWSE {industry}類指數",
            "change_pct": sector_change_pct,
            "constituents": constituents,
        })

    sectors.sort(
        key=lambda s: sum(c["mktcap"] or 0 for c in s["constituents"]),
        reverse=True,
    )
    return sectors


def fetch_twii_quote(errors: list) -> dict | None:
    """加權指數從 yf.py fetch_indices() 取，此處預留接口。"""
    return None


def fetch_tw_movers(
    errors: list,
    top_n: int = 10,
    min_mktcap: float = TW_MOVERS_MIN_MKTCAP,
    min_trade_value: float = TW_MOVERS_MIN_TRADE_VALUE,
) -> tuple[list[dict], list[dict]]:
    """
    從 STOCK_DAY_ALL 掃全上市，找當日漲跌幅最大個股。
    雙重門檻（AND）：市值 ≥ min_mktcap、成交金額 ≥ min_trade_value。
    每個 mover 帶 name + sector。回 (top_gainers, top_losers)。
    """
    try:
        stock_day = _fetch_stock_day_all()
    except Exception as e:
        errors.append({"source": "TWSE:STOCK_DAY_ALL", "stage": "highlights", "message": str(e)})
        return [], []

    try:
        shares_map = _fetch_company_shares()
    except Exception as e:
        errors.append({"source": "TWSE:MI_QFIIS", "stage": "highlights", "message": str(e)})
        shares_map = {}

    finmind_industry = _fetch_finmind_industry()

    movers = []
    for code, price_data in stock_day.items():
        price = price_data.get("price")
        change_pct = price_data.get("change_pct")
        if price is None or change_pct is None:
            continue
        shares = shares_map.get(code, 0)
        mktcap = price * shares if shares > 0 else 0
        if mktcap < min_mktcap:
            continue
        trade_value = price_data.get("trade_value", 0) or 0
        if trade_value < min_trade_value:
            continue
        name = price_data.get("name") or code
        sector = finmind_industry.get(code, "")
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
    losers = [_to_mover(m) for m in movers[-top_n:][::-1]]
    return gainers, losers
