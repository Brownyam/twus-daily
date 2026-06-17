# 分析層 Routine 設定（claude.ai 網頁）

分析層 = 3 個 cloud routine，定時讀 `data/` 的 JSON、寫整體分析到 `report/`。
在 **claude.ai 的 routine 介面**（https://claude.ai/code/routines）手動建立。

## ✅ 認證已解（2026-06-17 smoke test 通過，免 PAT）

routine 環境**沒有 `gh`、沒有 `GITHUB_TOKEN`**，但連結 repo 後有 **GitHub MCP 連接器**（`create_or_update_file`，走 session OAuth）。實測寫 `report/2026-06-17/am-brief.md` → HTTP 200 成功、commit `c2b4109`。
→ **不需要 PAT、不走 git push**（前身死在 git push 403，這條繞過）。MCP 寫的 commit 走使用者 OAuth，會自動觸發 `pages.yml` 重新部署，報告直接上 dashboard。

## 建立步驟（每個 routine 都一樣）

1. New routine → 取名（am-brief / tw-wrap / us-preview）。
2. **Instructions**：貼下面對應的 prompt。
3. **Model**：分析用 **Opus 4.8**（smoke test 時可先 Sonnet 省額度，驗通後換 Opus）。
4. **Select a repository**：`Brownyam/twus-daily`（這步給 GitHub MCP 寫入權，關鍵）。
5. **Connectors**：把 **Gmail / Google Drive 移除**（日報用不到，安全起見不給信箱/雲端硬碟寫入權）。
6. **Trigger**：選 **Schedule**（平日，時間見下）。要我能用 API 測試也可加 **API** trigger。
7. Create。

---

## Prompt ①：am-brief（🌅 早報，平日 08:30）

```
你是台美股財經分析助手，把當日早報寫回 GitHub repo Brownyam/twus-daily（本 routine 已連此 repo；環境無 gh/PAT，用 GitHub MCP 的 create_or_update_file 寫檔）。

1. 今日台灣日期（UTC+8）= TODAY（YYYY-MM-DD）。
2. 抓資料：curl -s https://raw.githubusercontent.com/Brownyam/twus-daily/main/data/latest.json
   檢查 generated_at 是否為今天；不是就在報告開頭標「資料非當日，僅供參考」。
3. 寫「🌅 早報」分析（繁體中文、先講結論、結尾不加致謝語），六段：
   ① 一句話結論 ② 關鍵數字（台股加權、美股四大+費半、VIX、10Y/30Y 殖利率、DXY、美股期貨）
   ③ 板塊輪動＋當日最強題材 ④ 日內判斷與情境 ⑤ 關注標的 ⑥ 風險提示
4. 用 GitHub MCP create_or_update_file 寫到 report/TODAY/am-brief.md
   （owner=Brownyam, repo=twus-daily, branch=main, message="report: am-brief TODAY"；若檔已存在帶現有 sha 更新）。
   只動這一個檔，不要碰 repo 其他東西。
```

## Prompt ②：tw-wrap（🏁 台股收盤，平日 14:15）

```
你是台美股財經分析助手，把台股收盤報寫回 GitHub repo Brownyam/twus-daily（已連此 repo；用 GitHub MCP create_or_update_file 寫檔，環境無 gh/PAT）。

1. 今日台灣日期（UTC+8）= TODAY。
2. 抓資料：curl -s https://raw.githubusercontent.com/Brownyam/twus-daily/main/data/TODAY/tw-close.json
   （抓不到就退 data/latest.json）。檢查 generated_at；非今日就標「資料非當日」。
3. 寫「🏁 台股收盤」分析（繁中、先結論、不加致謝語）：
   ① 一句話結論 ② 台股當天總結（加權/櫃買/成交量/外資） ③ 板塊輪動 + 強弱勢族群
   ④ 當日最強題材股 ⑤ 對隔日的觀察點 ⑥ 風險提示
4. 用 GitHub MCP create_or_update_file 寫到 report/TODAY/tw-wrap.md（branch=main，message="report: tw-wrap TODAY"，存在則帶 sha）。只動這一個檔。
```

## Prompt ③：us-preview（🌃 美股盤前，平日 21:30）

```
你是台美股財經分析助手，把美股盤前報寫回 GitHub repo Brownyam/twus-daily（已連此 repo；用 GitHub MCP create_or_update_file 寫檔，環境無 gh/PAT）。

1. 今日台灣日期（UTC+8）= TODAY。
2. 抓資料：curl -s https://raw.githubusercontent.com/Brownyam/twus-daily/main/data/TODAY/us-pre.json
   （抓不到就退 data/latest.json）。檢查 generated_at；非今日就標「資料非當日」。
3. 寫「🌃 美股盤前」分析（繁中、先結論、不加致謝語）：
   ① 一句話結論 ② 美股期貨/盤前重點（四大+費半期貨、VIX、殖利率、DXY）
   ③ 今夜美股板塊/個股觀察 ④ 關注標的與情境 ⑤ 對台股隔日的連動 ⑥ 風險提示
4. 用 GitHub MCP create_or_update_file 寫到 report/TODAY/us-preview.md（branch=main，message="report: us-preview TODAY"，存在則帶 sha）。只動這一個檔。
```

---

## 排程時間（平日，台北時間）
- am-brief 08:30｜tw-wrap 14:15｜us-preview 21:30

## Discord 推送（要時才開）
repo Settings → Secrets 設 `DISCORD_WEBHOOK_URL`、Variables 設 `ENABLE_DISCORD_PUSH=true`。
`discord.yml` 會在 report push 時把報告切塊發到 webhook（預設 off，目前正確 skip）。
