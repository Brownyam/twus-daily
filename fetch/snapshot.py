"""
fetch/snapshot.py
主入口：跑一個 slot → 組符合 schema 的 dict → 寫 data/{trading_day}/{slot}.json + {slot}.md + 更新 latest.json。

用法：
  py -3.12 fetch/snapshot.py --slot tw-close
  py -3.12 fetch/snapshot.py --slot tw-close --out-dir C:\\tmp\\altk_scratch\\twus_test
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import jsonschema

# ── 讓 fetch 套件可以用相對 import（從 repo root 執行）
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fetch.config import SCHEMA_VERSION, SLOTS
from fetch.mkt_calendar import get_market_status, get_trading_day, is_market_holiday
from fetch.sources.yf import fetch_indices, fetch_macro, fetch_us_sectors
from fetch.sources.twse import fetch_tw_sectors, fetch_tw_movers, fetch_tw_subgroups, fetch_tw_themes
from fetch.sources.crypto import fetch_crypto
from fetch.sources.news import fetch_news
from fetch.universe import build_highlights

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("snapshot")

TZ_TW = timezone(timedelta(hours=8))
SCHEMA_PATH = _REPO_ROOT / "schema" / "snapshot.schema.json"


# ──────────────────────────────────────────────
# Schema 驗證
# ──────────────────────────────────────────────

def _load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _validate(snapshot: dict, schema: dict) -> list[str]:
    """
    用 jsonschema 驗證 snapshot。
    回傳錯誤訊息 list（空 list = 通過）。
    """
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(snapshot), key=lambda e: list(e.absolute_path))
    return [f"{list(e.absolute_path)}: {e.message}" for e in errors]


# ──────────────────────────────────────────────
# 產 Markdown 人讀版
# ──────────────────────────────────────────────

def _to_markdown(snap: dict) -> str:
    """
    將 snapshot dict 轉成人讀 Markdown，段落之間用 ---SPLIT--- 分隔（給 Discord 切塊用）。
    """
    lines = []
    slot_label = snap.get("slot_label", snap.get("slot", ""))
    trading_day = snap.get("trading_day", "")
    generated_at = snap.get("generated_at", "")

    lines.append(f"# 📊 {slot_label}（{trading_day}）")
    lines.append(f"_資料時間：{generated_at}_")
    lines.append("")

    mstatus = snap.get("market_status", {})
    lines.append(f"**市場狀態** — 台股：{mstatus.get('tw', '-')}　美股：{mstatus.get('us', '-')}")
    lines.append("")

    # 假日快速結束
    if mstatus.get("tw") == "holiday" or mstatus.get("us") == "holiday":
        market_note = "台股" if mstatus.get("tw") == "holiday" else "美股"
        lines.append(f"⏸️ {market_note}今日休市，無交易數據。")
        return "\n".join(lines)

    lines.append("---SPLIT---")

    # 指數
    lines.append("## 指數")
    for idx in snap.get("indices", []):
        sym = idx.get("symbol", "")
        name = idx.get("name", sym)
        price = idx.get("price")
        cp = idx.get("change_pct")
        price_str = f"{price:,.2f}" if price is not None else "N/A"
        cp_str = f"{cp:+.2f}%" if cp is not None else "N/A"
        lines.append(f"- **{name}**（{sym}）{price_str}　{cp_str}")
    lines.append("")
    lines.append("---SPLIT---")

    # Macro
    macro = snap.get("macro", {})
    lines.append("## Macro")
    if macro.get("vix"):
        v = macro["vix"]
        lines.append(f"- VIX：{v.get('value')}　({v.get('change_pct', 0):+.2f}%)")
    if macro.get("us10y"):
        y = macro["us10y"]
        lines.append(f"- US 10Y：{y.get('value')}%　({y.get('change_bps', 0):+.0f} bps)")
    if macro.get("us30y"):
        y = macro["us30y"]
        lines.append(f"- US 30Y：{y.get('value')}%　({y.get('change_bps', 0):+.0f} bps)")
    if macro.get("dxy"):
        d = macro["dxy"]
        lines.append(f"- DXY：{d.get('value')}　({d.get('change_pct', 0):+.2f}%)")
    for fut in macro.get("futures", []):
        cp = fut.get("change_pct")
        cp_str = f"{cp:+.2f}%" if cp is not None else "N/A"
        lines.append(f"- {fut.get('name', fut.get('symbol'))}：{cp_str}")
    lines.append("")
    lines.append("---SPLIT---")

    # 板塊
    lines.append("## 美股板塊")
    for s in snap.get("sectors", {}).get("US", []):
        cp = s.get("change_pct")
        cp_str = f"{cp:+.2f}%" if cp is not None else "N/A"
        lines.append(f"- **{s['sector']}**（{s['etf']}）{cp_str}")
        for c in s.get("constituents", [])[:3]:
            ccp = c.get("change_pct")
            ccp_str = f"{ccp:+.2f}%" if ccp is not None else "N/A"
            lines.append(f"  - {c['symbol']}　{ccp_str}")
    lines.append("")

    lines.append("## 台股板塊（市值前五）")
    for s in snap.get("sectors", {}).get("TW", [])[:5]:
        cp = s.get("change_pct")
        cp_str = f"{cp:+.2f}%" if cp is not None else "N/A"
        lines.append(f"- **{s['sector']}**　{cp_str}")
        for c in s.get("constituents", [])[:3]:
            ccp = c.get("change_pct")
            ccp_str = f"{ccp:+.2f}%" if ccp is not None else "N/A"
            lines.append(f"  - {c['symbol']}　{ccp_str}")
    lines.append("")
    lines.append("---SPLIT---")

    # Highlights
    hl = snap.get("highlights", {})
    ss = hl.get("strongest_sector")
    if ss:
        lines.append(f"## 🏆 當日最強板塊：{ss['region']} {ss['sector']}（{ss.get('change_pct', 0):+.2f}%）")
        for leader in hl.get("sector_leaders", []):
            lcp = leader.get("change_pct")
            lcp_str = f"{lcp:+.2f}%" if lcp is not None else "N/A"
            lines.append(f"  - {leader.get('name', leader['symbol'])}（{leader['symbol']}）{lcp_str}")
    lines.append("")

    lines.append("**漲幅前段**")
    for m in hl.get("top_gainers", []):
        cp = m.get("change_pct")
        cp_str = f"{cp:+.2f}%" if cp is not None else "N/A"
        note = f" — {m['note']}" if m.get("note") else ""
        lines.append(f"- {m.get('name', m['symbol'])}（{m['symbol']}，{m.get('region', '')}）{cp_str}{note}")

    lines.append("")
    lines.append("**跌幅前段**")
    for m in hl.get("top_losers", []):
        cp = m.get("change_pct")
        cp_str = f"{cp:+.2f}%" if cp is not None else "N/A"
        note = f" — {m['note']}" if m.get("note") else ""
        lines.append(f"- {m.get('name', m['symbol'])}（{m['symbol']}，{m.get('region', '')}）{cp_str}{note}")

    lines.append("")
    lines.append("---SPLIT---")

    # 加密
    lines.append("## 加密貨幣")
    for c in snap.get("crypto", []):
        cp = c.get("change_pct_24h")
        cp_str = f"{cp:+.2f}%" if cp is not None else "N/A"
        price = c.get("price")
        price_str = f"${price:,.2f}" if price is not None else "N/A"
        lines.append(f"- **{c['symbol']}**　{price_str}　24h {cp_str}")
    lines.append("")
    lines.append("---SPLIT---")

    # 新聞
    lines.append("## 新聞")
    for n in snap.get("news", []):
        lines.append(f"- {n.get('tag', '')} **[{n.get('source', '')}]** {n.get('title', '')}")
        if n.get("summary"):
            lines.append(f"  {n['summary'][:120]}…")
        lines.append(f"  <{n.get('url', '')}>")
    lines.append("")

    # Errors
    errs = snap.get("errors", [])
    if errs:
        lines.append("---SPLIT---")
        lines.append("## ⚠️ 資料缺口（errors）")
        for e in errs:
            lines.append(f"- [{e.get('stage', '')}] {e.get('source', '')}：{e.get('message', '')}")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 組 minimal holiday snapshot
# ──────────────────────────────────────────────

def _build_holiday_snapshot(slot: str, trading_day: str, market_status: dict) -> dict:
    """
    假日時只寫最小 JSON（符合 schema required fields）。
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(TZ_TW).isoformat(),
        "slot": slot,
        "slot_label": SLOTS.get(slot, {}).get("label", slot),
        "trading_day": trading_day,
        "market_status": market_status,
        "indices": [],
        "macro": {"futures": []},
        "sectors": {"US": [], "TW": [], "TW_sub": [], "TW_chain": [], "TW_theme": []},
        "highlights": {
            "strongest_sector": None,
            "sector_leaders": [],
            "top_gainers": [],
            "top_losers": [],
        },
        "crypto": [],
        "news": [],
        "errors": [],
    }


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def build_snapshot(slot: str) -> dict:
    """
    組完整 snapshot dict。所有 source 失敗都 best-effort + errors[]。
    """
    errors: list[dict] = []
    trading_day = get_trading_day(slot)
    market_status = get_market_status(slot, trading_day)

    # 假日：只產 minimal JSON
    if is_market_holiday(slot, trading_day):
        logger.info(f"[{slot}] 市場休市，產 minimal snapshot")
        return _build_holiday_snapshot(slot, trading_day, market_status)

    logger.info(f"[{slot}] 開始抓取，trading_day={trading_day}")

    # ── 指數 ──
    logger.info("抓指數...")
    indices = fetch_indices(errors)

    # ── Macro ──
    logger.info("抓 Macro...")
    macro = fetch_macro(errors)

    # ── 美股板塊 ──
    logger.info("抓美股板塊...")
    us_sectors = fetch_us_sectors(errors)

    # ── 台股板塊（大分類）──
    logger.info("抓台股板塊...")
    tw_sectors = fetch_tw_sectors(errors)

    # ── 台股次產業 + 上下游供應鏈 + 題材鏈（電子家族，人工對照表）──
    logger.info("組台股次產業/供應鏈/題材鏈...")
    tw_sub_sectors, tw_chain_sectors = fetch_tw_subgroups(errors)
    tw_theme_sectors = fetch_tw_themes(errors)

    # ── 台股漲跌幅排行 ──
    logger.info("抓台股漲跌幅...")
    tw_gainers, tw_losers = fetch_tw_movers(errors)

    # ── Highlights ──
    logger.info("組 highlights...")
    highlights = build_highlights(us_sectors, tw_sectors, tw_gainers, tw_losers, errors)

    # ── 加密 ──
    logger.info("抓加密...")
    crypto = fetch_crypto(errors)

    # ── 新聞 ──
    logger.info("抓新聞...")
    news = fetch_news(errors)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(TZ_TW).isoformat(),
        "slot": slot,
        "slot_label": SLOTS.get(slot, {}).get("label", slot),
        "trading_day": trading_day,
        "market_status": market_status,
        "indices": indices,
        "macro": macro,
        "sectors": {
            "US": us_sectors,
            "TW": tw_sectors,
            "TW_sub": tw_sub_sectors,      # 次產業（電子家族）
            "TW_chain": tw_chain_sectors,  # 上下游供應鏈（上/中/下游）
            "TW_theme": tw_theme_sectors,  # 題材鏈（CoWoS/HBM/CPO/Rack電源/機器人…，多對多）
        },
        "highlights": highlights,
        "crypto": crypto,
        "news": news,
        "errors": errors,
    }

    return snapshot


def write_outputs(snapshot: dict, out_dir: Path) -> tuple[Path, Path, Path]:
    """
    寫 JSON + MD + latest.json。
    回傳 (json_path, md_path, latest_path)。
    """
    trading_day = snapshot["trading_day"]
    slot = snapshot["slot"]

    day_dir = out_dir / trading_day
    day_dir.mkdir(parents=True, exist_ok=True)

    json_path = day_dir / f"{slot}.json"
    md_path = day_dir / f"{slot}.md"
    latest_path = out_dir / "latest.json"

    # 寫 JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(f"寫入 JSON：{json_path}")

    # 寫 MD
    md_content = _to_markdown(snapshot)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info(f"寫入 MD：{md_path}")

    # 更新 latest.json
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    logger.info(f"更新 latest.json：{latest_path}")

    return json_path, md_path, latest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="twus-daily snapshot 抓取")
    parser.add_argument(
        "--slot",
        required=True,
        choices=list(SLOTS.keys()),
        help="時段：tw-pre | tw-mid | tw-close | us-pre | us-mid",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="輸出目錄（預設：repo 根目錄 data/）",
    )
    args = parser.parse_args()

    # 決定輸出目錄
    if args.out_dir:
        out_dir = args.out_dir.resolve()
    else:
        out_dir = _REPO_ROOT / "data"

    logger.info(f"slot={args.slot}，out_dir={out_dir}")

    # 建 snapshot
    snapshot = build_snapshot(args.slot)

    # Schema 驗證
    try:
        schema = _load_schema()
        validation_errors = _validate(snapshot, schema)
        if validation_errors:
            logger.error(f"⚠️  Schema 驗證失敗（{len(validation_errors)} 項）：")
            for ve in validation_errors:
                logger.error(f"  {ve}")
        else:
            logger.info("✅ Schema 驗證通過")
    except Exception as e:
        logger.error(f"Schema 載入失敗：{e}")

    # 寫檔
    json_path, md_path, latest_path = write_outputs(snapshot, out_dir)

    # 回報摘要
    errors = snapshot.get("errors", [])
    logger.info(
        f"\n=== 完成 ===\n"
        f"  JSON：{json_path}\n"
        f"  MD  ：{md_path}\n"
        f"  errors 數量：{len(errors)}"
    )
    if errors:
        logger.info("  errors 清單：")
        for e in errors:
            logger.info(f"    [{e['stage']}] {e['source']}：{e['message']}")


if __name__ == "__main__":
    main()
