"""
fetch/calendar.py
假日判斷 + slot→market_status。
判斷日期用台灣時間（UTC+8），不是 GHA 的 UTC。
"""

from datetime import datetime, timezone, timedelta
from typing import Literal

import exchange_calendars as xcals

# 台灣時區
TZ_TW = timezone(timedelta(hours=8))

# exchange_calendars 中的交易所代碼
CAL_TW = "XTAI"
CAL_US = "XNYS"


def _today_tw() -> str:
    """回傳台灣今日日期字串 YYYY-MM-DD。"""
    return datetime.now(TZ_TW).strftime("%Y-%m-%d")


def is_trading_day(exchange: str, date_str: str) -> bool:
    """
    判斷 date_str（YYYY-MM-DD）是否為 exchange 的交易日。
    exchange：CAL_TW 或 CAL_US。
    """
    cal = xcals.get_calendar(exchange)
    return cal.is_session(date_str)


def get_market_status(
    slot: str,
    date_str: str | None = None,
) -> dict[str, str]:
    """
    根據 slot 與日期，回傳 {"tw": <state>, "us": <state>}。
    state：pre | open | closed | holiday。

    slot 決定哪個市場要做假日過濾：
    - tw-pre/tw-mid/tw-close → TW 市場用 XTAI 判斷
    - us-pre/us-mid          → US 市場用 XNYS 判斷
    對應市場若休市則回傳 holiday；對方市場根據時段給合理預設。
    """
    if date_str is None:
        date_str = _today_tw()

    tw_trading = is_trading_day(CAL_TW, date_str)
    us_trading = is_trading_day(CAL_US, date_str)

    # 根據 slot 設定各市場狀態
    if slot == "tw-pre":
        tw_state = "pre" if tw_trading else "holiday"
        us_state = "closed"  # 盤前時美股已收盤
    elif slot == "tw-mid":
        tw_state = "open" if tw_trading else "holiday"
        us_state = "closed"
    elif slot == "tw-close":
        tw_state = "closed" if tw_trading else "holiday"
        us_state = "closed"
    elif slot == "us-pre":
        tw_state = "closed"
        us_state = "pre" if us_trading else "holiday"
    elif slot == "us-mid":
        tw_state = "closed"
        us_state = "open" if us_trading else "holiday"
    else:
        tw_state = "closed"
        us_state = "closed"

    return {"tw": tw_state, "us": us_state}


def is_market_holiday(slot: str, date_str: str | None = None) -> bool:
    """
    判斷這個 slot 的主要市場今天是否放假。
    tw-* slot → 看 XTAI；us-* slot → 看 XNYS。
    回傳 True 表示應 skip 完整抓取，只寫 minimal JSON。
    """
    if date_str is None:
        date_str = _today_tw()

    if slot.startswith("tw-"):
        return not is_trading_day(CAL_TW, date_str)
    else:
        return not is_trading_day(CAL_US, date_str)


def get_trading_day(slot: str | None = None) -> str:
    """
    回傳本次 snapshot 的 trading_day（台灣時間今日 YYYY-MM-DD）。
    slot 參數預留未來有需要時細分（例如美股盤中算「明日」台股交易日）。
    """
    return _today_tw()
