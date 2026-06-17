"""Discord 發送模組：讀分析報告 md → 切塊 → POST webhook。

webhook 讀取序：環境變數 DISCORD_WEBHOOK_URL → repo 根 .env。
前身踩坑：① Discord 擋預設 urllib UA（403）→ 帶自訂 User-Agent；
         ② 單訊息上限 2000 字 → 先按 ---SPLIT--- 分段、每段再 1900 切塊。

用法：python discord/post.py --report report/2026-06-17/am-brief.md
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests

MAX_CHARS = 1900
USER_AGENT = "TWUSDailyBot/1.0 (+https://github.com/Brownyam/twus-daily)"


def load_webhook() -> str:
    """env 優先，其次 repo 根 .env（已 gitignore）。"""
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if url:
        return url
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == "DISCORD_WEBHOOK_URL":
                return val.strip().strip('"').strip("'")
    return ""


def split_message(text: str):
    """先按 ---SPLIT--- 分段，每段再按 MAX_CHARS（盡量在換行處）切塊。"""
    chunks = []
    for section in text.split("---SPLIT---"):
        section = section.strip()
        while len(section) > MAX_CHARS:
            cut = section.rfind("\n", 0, MAX_CHARS)
            if cut <= 0:
                cut = MAX_CHARS
            chunks.append(section[:cut].rstrip())
            section = section[cut:].lstrip()
        if section:
            chunks.append(section)
    return chunks


def post(webhook: str, content: str) -> None:
    resp = requests.post(
        webhook,
        json={"content": content},
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True, help="報告 md 檔路徑")
    args = ap.parse_args()

    report_path = Path(args.report)
    if not report_path.exists():
        print(f"[ERROR] 找不到報告：{report_path}", file=sys.stderr)
        return 1

    webhook = load_webhook()
    if not webhook.startswith("https://discord.com/api/webhooks/"):
        print("[ERROR] 缺少有效的 DISCORD_WEBHOOK_URL（env 或 .env）", file=sys.stderr)
        return 1

    chunks = split_message(report_path.read_text(encoding="utf-8"))
    if not chunks:
        print("[WARN] 報告無內容可發")
        return 0

    for i, chunk in enumerate(chunks, 1):
        post(webhook, chunk)
        print(f"已發送 {i}/{len(chunks)}（{len(chunk)} 字）")
        if i < len(chunks):
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
