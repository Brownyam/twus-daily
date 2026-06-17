"""
fetch/universe.py
動態 universe 建構：
- 美股：各板塊 ETF top-10 holdings（來自 yf.py 已抓的 sectors）
- 台股：各產業市值前十（來自 twse.py 已抓的 sectors）
- 當日最強：strongest_sector + sector_leaders + top_gainers/losers
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_highlights(
    us_sectors: list[dict],
    tw_sectors: list[dict],
    tw_gainers: list[dict],
    tw_losers: list[dict],
    errors: list,
) -> dict:
    """
    組 highlights 區塊：
    - strongest_sector：US vs TW 哪個板塊漲最多
    - sector_leaders：最強板塊裡 change_pct 前幾名個股
    - top_gainers / top_losers：全市場（TW 已由 twse 提供，US 從 sectors 聯集）

    回傳符合 schema highlights 格式的 dict。
    """
    # ── 找最強板塊 ──
    best_us: dict | None = None
    for s in us_sectors:
        cp = s.get("change_pct")
        if cp is None:
            continue
        if best_us is None or cp > best_us["change_pct"]:
            best_us = {"region": "US", "sector": s["sector"], "change_pct": cp}

    best_tw: dict | None = None
    for s in tw_sectors:
        cp = s.get("change_pct")
        if cp is None:
            continue
        if best_tw is None or cp > best_tw["change_pct"]:
            best_tw = {"region": "TW", "sector": s["sector"], "change_pct": cp}

    # 比較 TW vs US
    strongest_sector: dict | None = None
    if best_us and best_tw:
        strongest_sector = best_us if best_us["change_pct"] >= best_tw["change_pct"] else best_tw
    elif best_us:
        strongest_sector = best_us
    elif best_tw:
        strongest_sector = best_tw

    # ── sector_leaders：最強板塊前 3 個股 ──
    sector_leaders: list[dict] = []
    if strongest_sector:
        source_sectors = us_sectors if strongest_sector["region"] == "US" else tw_sectors
        for s in source_sectors:
            if s["sector"] == strongest_sector["sector"]:
                # 按 change_pct 排序
                members = [
                    c for c in s.get("constituents", [])
                    if c.get("change_pct") is not None
                ]
                members.sort(key=lambda x: x["change_pct"], reverse=True)
                sector_leaders = [
                    {"symbol": m["symbol"], "name": m.get("name", m["symbol"]),
                     "change_pct": m["change_pct"]}
                    for m in members[:3]
                ]
                break

    # ── top_gainers / top_losers：合併 TW 個股 + US 板塊成分 ──
    us_movers: list[dict] = []
    for s in us_sectors:
        for c in s.get("constituents", []):
            if c.get("change_pct") is not None:
                us_movers.append({
                    "symbol": c["symbol"],
                    "name": c.get("name", c["symbol"]),
                    "region": "US",
                    "change_pct": c["change_pct"],
                    "note": "",
                })

    # 去重（US movers 跨 ETF 可能重複）
    seen = set()
    us_movers_dedup = []
    for m in us_movers:
        if m["symbol"] not in seen:
            seen.add(m["symbol"])
            us_movers_dedup.append(m)

    all_movers = tw_gainers + us_movers_dedup
    all_movers.sort(key=lambda x: x.get("change_pct") or 0, reverse=True)

    top_gainers = [
        {"symbol": m["symbol"], "name": m.get("name", ""), "region": m["region"],
         "change_pct": m["change_pct"], "note": m.get("note", "")}
        for m in all_movers[:5]
    ]

    # losers：TW losers + US 最差個股
    us_movers_dedup.sort(key=lambda x: x.get("change_pct") or 0)
    all_losers = tw_losers + us_movers_dedup[:5]
    all_losers.sort(key=lambda x: x.get("change_pct") or 0)

    top_losers = [
        {"symbol": m["symbol"], "name": m.get("name", ""), "region": m["region"],
         "change_pct": m["change_pct"], "note": m.get("note", "")}
        for m in all_losers[:5]
    ]

    return {
        "strongest_sector": strongest_sector,
        "sector_leaders": sector_leaders,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
    }
