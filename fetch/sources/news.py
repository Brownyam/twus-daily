"""
fetch/sources/news.py
新聞抓取：feedparser RSS + Anue JSON API + deep_translator 翻中（best-effort）。
單一源失敗只記 errors[]，不中斷。
"""

from __future__ import annotations

import logging
from typing import Any

import urllib3
import feedparser
import requests

# Windows 環境可能出現 SSL 憑證驗證問題，suppress InsecureRequest 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from fetch.config import (
    NEWS_PER_SOURCE,
    RSS_FEEDS,
    TRANSLATE_DST,
    TRANSLATE_SRC,
    TRANSLATOR_SERVICE,
)

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 twus-daily-bot/1.0"}
_TIMEOUT = 15


def _translate(text: str) -> str:
    """
    用 deep_translator 翻譯 text → 繁體中文。
    失敗回傳原文（best-effort）。
    """
    if not text or not text.strip():
        return text
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source=TRANSLATE_SRC, target=TRANSLATE_DST).translate(text)
        return translated or text
    except Exception as e:
        logger.warning(f"翻譯失敗: {e}")
        return text


def _fetch_rss(feed_meta: dict, errors: list) -> list[dict]:
    """
    feedparser 抓 RSS，取最新 NEWS_PER_SOURCE 條。
    SSL 問題（Windows 憑證）：先用 requests 下載，再交 feedparser 解析。
    """
    source = feed_meta["source"]
    url = feed_meta["url"]
    tag = feed_meta["tag"]
    need_translate = feed_meta.get("translate", False)

    try:
        # 用 requests 先下載 feed content（有時 feedparser 直接存取 SSL 失敗）
        try:
            raw_resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, verify=False)
            raw_resp.raise_for_status()
            parsed = feedparser.parse(raw_resp.content)
        except Exception:
            # fallback：直接讓 feedparser 存取
            parsed = feedparser.parse(url, request_headers=_HEADERS)

        if parsed.bozo and not parsed.entries:
            raise ValueError(f"feedparser 解析失敗: {parsed.bozo_exception}")

        items = []
        for entry in parsed.entries[:NEWS_PER_SOURCE]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary_raw = entry.get("summary", entry.get("description", "")).strip()
            # 去除 HTML tags（簡單處理）
            import re
            summary = re.sub(r"<[^>]+>", "", summary_raw).strip()

            published = ""
            if hasattr(entry, "published"):
                published = entry.published
            elif hasattr(entry, "updated"):
                published = entry.updated

            if need_translate:
                title = _translate(title)
                if summary:
                    summary = _translate(summary)

            items.append({
                "source": source,
                "tag": tag,
                "title": title,
                "summary": summary,
                "url": link,
                "published": published,
                "translated": need_translate,
            })
        return items

    except Exception as e:
        errors.append({
            "source": source,
            "stage": "news",
            "message": f"RSS 抓取失敗: {e}",
        })
        return []


def _fetch_anue_json(feed_meta: dict, errors: list) -> list[dict]:
    """
    鉅亨網 JSON API 特殊處理。
    實際回應結構（2026-06 驗證）：
      { "items": { "total": N, "data": [...], ... }, "statusCode": 200 }
    """
    source = feed_meta["source"]
    url = feed_meta["url"]
    tag = feed_meta["tag"]

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # 正確路徑：data['items']['data']
        raw_items = []
        items_block = data.get("items")
        if isinstance(items_block, dict):
            raw_items = items_block.get("data", [])
        elif isinstance(items_block, list):
            raw_items = items_block
        else:
            # fallback：嘗試其他常見路徑
            for key in ["news", "list", "results", "data"]:
                candidate = data.get(key, [])
                if isinstance(candidate, list) and candidate:
                    raw_items = candidate
                    break

        items = []
        for item in raw_items[:NEWS_PER_SOURCE]:
            title = str(item.get("title", "")).strip()
            news_id = item.get("newsId", "")
            url_link = f"https://news.cnyes.com/news/id/{news_id}" if news_id else ""
            summary = str(item.get("summary", item.get("content", ""))).strip()
            # publishAt 是 Unix timestamp（秒）
            pub_ts = item.get("publishAt")
            if pub_ts:
                try:
                    from datetime import datetime, timezone
                    published = datetime.fromtimestamp(int(pub_ts), tz=timezone.utc).isoformat()
                except Exception:
                    published = str(pub_ts)
            else:
                published = ""

            items.append({
                "source": source,
                "tag": tag,
                "title": title,
                "summary": summary,
                "url": url_link,
                "published": published,
                "translated": False,
            })
        return items

    except Exception as e:
        errors.append({
            "source": source,
            "stage": "news",
            "message": f"Anue JSON API 失敗: {e}",
        })
        return []


def fetch_news(errors: list) -> list[dict]:
    """
    主要對外介面。遍歷 RSS_FEEDS，抓新聞，翻譯英文源。
    單源失敗只記 errors，回傳其餘成功結果。
    """
    all_news = []

    for feed_meta in RSS_FEEDS:
        kind = feed_meta.get("kind", "rss")
        if kind == "json_api":
            items = _fetch_anue_json(feed_meta, errors)
        else:
            items = _fetch_rss(feed_meta, errors)

        # 過濾掉 title 為空的條目
        items = [i for i in items if i.get("title")]
        all_news.extend(items)

    return all_news
