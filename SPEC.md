# 每日台美股日報系統 v2 — 實作 Spec（定稿，給 Codex）

> 版本：2026-06-15 定稿（已納入外部 review 的 B2/B3/S2/S3 修正）
> 撰寫：Claude (Opus 4.8) 設計，交 Codex 實作
> 語言：本文件繁中；程式碼/schema/symbol 用英文

---

## 0. 決策已鎖定（Codex 不要自己改方向）

| 項目 | 決定 |
|---|---|
| 主交付 | **網站**（GitHub Pages dashboard），Discord 接口照做但**預設關閉** |
| **Repo** | **獨立 public repo**：`Brownyam/twus-daily`（名稱可改）。整個 repo 就是本系統，**不放進 claude-workspace**（claude-workspace 是私庫且含 alt_killer secret，不能設 public；Pages 免費方案要 public） |
| 架構 | **全 cloud**：GHA cron 跑數據腳本 + Anthropic routine 跑分析 + GHA 代發 Discord。零本機排程（Mac 移植零成本） |
| 兩層 | **數據快報層**（便宜、高頻、抓報價+新聞）／**分析層**（Opus routine、低頻、3 anchor 整體判斷） |
| **Push 機制** | 數據層用 GHA 內建 `GITHUB_TOKEN`（可靠）；分析層 routine **主走 GitHub Contents API**（`PUT /repos/.../contents/{path}`，打 api.github.com，避開 git credential）。git push 為**備案**，且**僅在 1 個 routine smoke test 證明可 push 才用**——前身正是死在 routine `git push` 連續 HTTP 403（見下歷史背景） |
| 加密 | 只留 **BTC / ETH** 當風險情緒參考 |
| 個股 | **動態 universe**：板塊市值前十 + 當日最強，不寫死清單 |
| 語言 | 報告繁中、先結論、不加致謝語 |
| 跨平台 | Python 用 `pathlib`/`Path.home()`，不 hardcode home；webhook 從 env / 本 repo 自己的 `.env` 讀（**不沾 alt_killer**） |

### 歷史背景（給 Codex 的脈絡，避免重踩）

- 本系統有「前身」：2026-05 跑過一套 5-slot 日報，2026-05-11 repo 大重整時**人為捨棄重做**（不是被 bug 搞死），cloud routine 被 Paused、schtasks 刪除。
- 前身的真實死因（一手來源 `handoff/2026-05-13_daily-report-rebuild.md` line 6）：5 個 routine `git commit` 都成功，但 **`git push origin main` 全部 HTTP 403**，root cause 未定論（GitHub App 面板顯示 R/W，但 routine sandbox 拿不到合法 push token）。**這才是 5/9 後報告空白的原因**。Discord 的 403 是另一個更早、已解決的坑（urllib 預設 UA 被擋）。**因此本版 routine 寫檔主走 GitHub Contents API，git push 僅在 smoke test 證明可行才用——不要優先重試一個已知 403 的機制。**

---

## 1. Repo 目錄結構

整個 `twus-daily` repo（root 就是系統根，無 `market/` 前綴）：

```
twus-daily/
  fetch/
    config.py          # 板塊定義、資產清單、新聞源、slot 表（單一設定源）
    universe.py        # 動態 universe：板塊→市值前十 + 當日最強
    snapshot.py        # 主入口：跑一個 slot → 寫 JSON + md
    calendar.py        # exchange_calendars 假日判斷
    sources/
      yf.py            # yfinance：指數/板塊/個股/VIX/殖利率/DXY/期貨
      twse.py          # TWSE+TPEx OpenAPI：加權/櫃買/類股指數/產業別/市值
      crypto.py        # CoinGecko：BTC/ETH
      news.py          # RSS + 翻譯（best-effort）
  schema/
    snapshot.schema.json
  data/                # 數據層輸出（網站吃）；保留策略見 §11
    YYYY-MM-DD/{slot}.json + {slot}.md
    latest.json        # 指向最新 snapshot（首頁快取）
  report/              # 分析層輸出（routine 寫）
    YYYY-MM-DD/{anchor}.md
  site/                # GitHub Pages 靜態站（無 build step）
    index.html  app.js  style.css
  discord/
    post.py            # Discord 發送模組（webhook + UA + split）
  .github/workflows/
    fetch.yml          # cron 跑 snapshot.py（5 slot）
    pages.yml          # 組 site + data → 部署 Pages
    discord.yml        # report push → 發 Discord（預設 off）
  requirements.txt
  .env.example         # DISCORD_WEBHOOK_URL=...（實際 .env 不 commit）
  README.md
  SPEC.md              # 本文件
```

---

## 2. JSON Schema（網站吃的結構化輸出 — 新建重點）

每個 slot 產一份 JSON。前身只吐 markdown，網站拿不到結構化資料，這是本版重點。

```jsonc
{
  "schema_version": "1.0",
  "generated_at": "2026-06-15T08:00:05+08:00",  // 帶時區；routine 用它確認是今日資料
  "slot": "tw-pre",                 // tw-pre|tw-mid|tw-close|us-pre|us-mid
  "slot_label": "台股盤前",
  "trading_day": "2026-06-15",
  "market_status": { "tw": "pre", "us": "closed" },   // pre|open|closed|holiday
  "indices": [
    { "symbol":"^TWII","name":"加權指數","region":"TW","price":0,"change":0,"change_pct":0,"prev_close":0 }
  ],
  "macro": {
    "vix":   { "symbol":"^VIX","value":0,"change_pct":0 },
    "us10y": { "symbol":"^TNX","value":0,"change_bps":0 },  // ^TNX 回的是殖利率值(如 4.25)，change_bps = (今-昨)*100，注意單位
    "us30y": { "symbol":"^TYX","value":0,"change_bps":0 },
    "dxy":   { "symbol":"DX-Y.NYB","value":0,"change_pct":0 },
    "futures": [ { "symbol":"ES=F","name":"標普期","change_pct":0 } ]
  },
  "sectors": {
    "US": [ { "sector":"科技","etf":"XLK","change_pct":0,
              "constituents":[ { "symbol":"AAPL","name":"Apple","weight_pct":0,"mktcap":0,"change_pct":0 } ] } ],
    "TW": [ { "sector":"半導體","index":"TWSE 半導體類指數","change_pct":0,
              "constituents":[ { "symbol":"2330.TW","name":"台積電","mktcap":0,"change_pct":0 } ] } ]
  },
  "highlights": {
    "strongest_sector": { "region":"US","sector":"科技","change_pct":0 },
    "sector_leaders":   [ { "symbol":"NVDA","change_pct":0 } ],
    "top_gainers":      [ { "symbol":"3661.TW","region":"TW","change_pct":0,"note":"題材" } ],
    "top_losers":       [ { "symbol":"...","region":"...","change_pct":0 } ]
  },
  "crypto": [ { "symbol":"BTC","price":0,"change_pct_24h":0 } ],
  "news": [ { "source":"鉅亨網","tag":"🇹🇼","title":"…","summary":"…","url":"…","published":"…","translated":false } ],
  "errors": [ { "source":"工商時報","stage":"news","message":"HTTP 410" } ]
}
```

**`errors[]` 是設計重點**：best-effort 抓取，任何單一源失敗不中斷，把失敗記進 JSON，網站可顯示「某源暫時失效」、Codex 好 debug。同時寫一份人讀版 `{slot}.md`（給 Discord/備份，段落用 `---SPLIT---` 分隔）。

---

## 3. 動態 Universe 建構邏輯（`universe.py`）

**美股**（乾淨）：
- 11 SPDR 板塊 ETF：`XLK XLF XLE XLV XLY XLP XLI XLU XLB XLC XLRE` + `SOXX`（半導）
- 每板塊取 **top-10 holdings**（市值權重前十）。來源優先序：① yfinance `Ticker(etf).funds_data.top_holdings` ② fallback ETF 發行商每日 holdings 檔。⚠️ **11 檔 `XL*` 是 SSGA/SPDR（`ssga.com/...holdings-daily-us-en-{etf}.xlsx`），但 `SOXX` 是 iShares/BlackRock，holdings fallback 來源不同（走 ishares.com，或半導體改用 SPDR 的 `XSD`）——config 標明 SOXX 別套 SSGA URL（會 404）**
- 板塊漲跌 = ETF 當日 change_pct（直接用 ETF，不用個股平均）

**台股**（⚠️ 唯一結構性風險，Codex 第一步先 spike 驗源）：
- 產業別分類：TWSE OpenAPI `t187ap03_L`（上市公司基本資料含產業別）
- 類股指數漲跌：TWSE OpenAPI `MI_INDEX`（含各類股指數，**台股板塊表現直接用這個，不用個股平均**）
- 個股當日收盤：`STOCK_DAY_ALL`（全上市）
- **⚠️ 市值 = 收盤價 × 發行股數，但「發行股數」不在上面任何 endpoint**：
  - `STOCK_DAY_ALL` 只有價格成交量，無股數
  - `t187ap03_L` 給的是「實收資本額」不是流通股數
  - **spike 必須先確認發行股數來源**：候選 ① FinMind `TaiwanStockInfo`/股本資料 ② TWSE 月報 ③ 用實收資本額 ÷ 面額10元 估算（粗略）
  - 驗不出乾淨股數，市值前十就排不出來——這是整套唯一會卡死的點，第一步先解
- 候選備源：整套 TWSE 不穩就改 FinMind（`TaiwanStockInfo` 產業別 + 價格 + 股本）。挑定寫進 config 註解

**當日最強**（每天重算）：
- `strongest_sector`：US 比 12 ETF change_pct；TW 比類股指數 change_pct
- `sector_leaders`：最強板塊裡 change_pct 前幾名個股
- `top_gainers/losers`：全市場掃當日漲跌幅（TW 用 `STOCK_DAY_ALL` 全掃 + 成交量/額過濾去雞蛋水餃；US 用 universe 聯集 + 大型股清單），取題材最強

> universe = 「板塊前十」（結構，慢變）+「當日最強」（動態，每天變）兩層疊加，零手動維護。

---

## 4. 完整資產 + 新聞源清單（`config.py`）

分 **Tier-1 核心（穩、必抓）** 與 **Tier-2 best-effort（抓不到不報錯，記 errors[]）**：

**指數**
- T1：台股 `^TWII`(加權)、美股 `^GSPC ^IXIC ^DJI ^NDX ^RUT ^SOX`(費半)
- T2：櫃買（TPEx OpenAPI）、國際 `^N225 ^KS11 ^HSI 000001.SS ^GDAXI ^FTSE`（次要參考）

**Macro（前身缺口，全補）**
- T1：`^VIX`、美債 10Y `^TNX` + 30Y `^TYX`、美元指數 `DX-Y.NYB`、美股期貨 `ES=F NQ=F YM=F RTY=F`
- T2：2Y 殖利率（yfinance 無乾淨源，抓不到留空）、台指期（TAIFEX OpenAPI，抓不到用 `^TWII` 代理）

**板塊**：US 12 ETF（見 §3）／TW 類股指數（TWSE MI_INDEX）

**加密**：BTC、ETH（CoinGecko `simple/price` + 24h 漲跌；⚠️ CoinGecko free tier 部分 endpoint 現需 demo key + rate limit 轉嚴，抓不到 fallback yfinance `BTC-USD`/`ETH-USD`）

**新聞源（best-effort 廣撒，單源失敗只記 errors[]）**
- 台股：鉅亨網（cnyes JSON API）、經濟日報、工商時報、中央社財經、Anue、MoneyDJ
- 美股/macro：CNBC、MarketWatch、Yahoo Finance、Investing.com、Nikkei Asia
- 加密（少量風險情緒）：CoinDesk、BlockTempo
- **起手清單拿掉**：Reuters Business（RSS 已大致停用/付費牆）、ZeroHedge（雜訊偏多，財經報告引用觀感差）
- 英文源經 `deep-translator` 翻中（失敗留原文）；每源取最新 1–2 條
- 前身那 14 條 RSS 當起點，能加就加。所有 feed 收進 `config.RSS_FEEDS`，標 tag + 是否需翻譯

---

## 5. 時段表（slot / anchor，全 TST）

**數據快報層**（`fetch.yml` cron，便宜）：

| slot | 標題 | TST | UTC cron | 假日過濾 |
|---|---|---|---|---|
| `tw-pre` | 台股盤前 | 08:00 | `0 0 * * 1-5` | TW |
| `tw-mid` | 台股盤中 | 11:00 | `0 3 * * 1-5` | TW |
| `tw-close` | 台股盤後 | 13:45 | `45 5 * * 1-5` | TW |
| `us-pre` | 美股盤前 | 21:00 | `0 13 * * 1-5` | US |
| `us-mid` | 美股盤中 | 23:30 | `30 15 * * 1-5` | US |

**分析層**（Anthropic routine，3 anchor，燒 Opus）——**時間刻意比對應 slot 晚 30 分，避開抓取/push 的 race**：

| anchor | 報告 | TST | 讀哪些 slot | 內容 |
|---|---|---|---|---|
| `am-brief` | 🌅 早報（主） | **08:30** | us-mid（昨）+ tw-pre | 美股昨夜收盤回顧 + 今日台股展望 + 日內判斷 |
| `tw-wrap` | 🏁 台股收盤 | **14:15** | tw-close | 台股當天總結 + 板塊輪動 |
| `us-preview` | 🌃 美股盤前 | **21:30** | us-pre | 展望美股當夜 + 關注標的 |

- 美股盤後（台灣清晨）不單發，併入隔天 `am-brief`。
- **race 防護（雙保險）**：① anchor 比 slot 晚 30 分（吸收 GHA cron ±5–15 分 lag + 腳本執行）② routine 讀 JSON 後**先檢查 `generated_at` 是今日**，不是就略過該段、改引用上一份有效 snapshot 並標註。

---

## 6. 假日 filter（`calendar.py`）

- `exchange_calendars`：`XTAI`（台）、`XNYS`（美）
- TW slot 遇 `XTAI` 非交易日 → skip 抓取，仍寫一份 `market_status.tw="holiday"` 的 minimal JSON（網站顯示休市）
- US slot 同理用 `XNYS`
- 判斷日期用 **台灣時間 today**（`timezone(+8)`），不是 GHA 的 UTC
- routine 也要 holiday-aware：對應市場休市時寫精簡版（一句結論 + 跨市場簡述），不寫長報告

---

## 7. 網站結構（`site/`，GitHub Pages on `twus-daily`）

純 vanilla HTML/CSS/JS（**無 build step**，跨平台零維護），CDN 引 `marked.js`（render 報告 md）。版面由上而下：

1. **Header**：日期 + 台股/美股狀態燈（盤前/盤中/收盤/休市）+ slot 切換 + 歷史日期 picker
2. **當日最強卡**：最強板塊 + 領漲股 + 題材股（首頁最顯眼）
3. **指數區**：台股（加權/櫃買/台指期）｜美股四大+費半+期貨｜國際（摺疊）
4. **Macro 區**：VIX／10Y・30Y 殖利率／DXY，配風險情緒燈（綠/黃/紅）
5. **板塊熱力圖**：US 12 + TW 各類股，CSS grid 色塊深淺 = 漲跌幅，點開看前十成分
6. **加密小區**：BTC/ETH
7. **新聞流**：依 tag 分類（🇹🇼/🇺🇸/🪙）
8. **分析報告區**：render 最新 routine 的 report md

資料來源：`fetch('./data/{date}/{slot}.json')` + `./report/{date}/{anchor}.md`。`latest.json` 給首頁預設載入。Pages 部署由 `pages.yml` 把 `site/` + `data/` + `report/` 組成 artifact 發佈（data 公開無妨，市場評論不機密）。歷史日期 picker 上限 = §11 的資料保留天數（超過天數的日期已被清，會 404，UI 要 disable）。

---

## 8. 分析層 Routine（3 個 Anthropic routine）

每個 routine 流程：
1. 取得當日數據 JSON（GET `raw.githubusercontent.com/.../data/{today}/{slot}.json`，或 git pull）
2. **先驗 `generated_at` 是今日**，不是就引用上一份有效 snapshot 並標註
3. 寫整體分析 → `report/{today}/{anchor}.md`
4. **用 GitHub Contents API `PUT /repos/Brownyam/twus-daily/contents/report/{today}/{anchor}.md`**（committer email = `daily-report-bot@users.noreply.github.com`，給 Discord workflow 當 gate）。PUT 會直接在 remote 產生 commit、觸發 Discord workflow。git push 為備案

**上線順序（重要，取代「一次開 3 個」）**：前身正是死在 routine `git push` 連續 HTTP 403，所以**先證明有一條能寫進 repo 的路，再 scale**：
1. 先只建 `am-brief` 一個 routine，**用 Contents API 寫一個 test 檔，確認真的進了 repo（write smoke test）**
2. Contents API 通過 → 建 `tw-wrap` + `us-preview`，全部走 Contents API
3. 若想改用 git push（較省事），**必須先用 1 個 routine 實測 push 成功**（前身在這死過，不要假設它會通）；push 也 403 就維持 Contents API，**不要硬調 git 憑證**

Routine prompt 骨架（繁中、先結論、不致謝、holiday-aware）：
```
你是台美股財經分析助手。讀附帶的 JSON 數據，產出 {anchor 報告}。
輸出結構：① 一句結論 ② 關鍵數字（指數/macro/期貨）③ 板塊輪動 + 當日最強題材
④ 日內判斷與情境 ⑤ 關注標的 ⑥ 風險提示。
規則：先結論再細節、繁中口語、不要 markdown 表格堆疊、結尾不加致謝語。
若對應市場今日休市，只寫精簡版（結論 + 跨市場簡述）。
段落用 ---SPLIT--- 分隔（給 Discord 切塊用）。
```
Model：`claude-opus-4-8`。
> ⚠️ 配額提醒：3 個 Opus routine/天。若訂閱降 Pro、5-hour 額度吃緊，可把分析層改 `claude-sonnet-4-6`（成本低很多，日報分析夠用）。

---

## 9. Discord 接口（做好但預設 off）

- `discord/post.py`：讀 report md（或 JSON 組摘要）→ 按 `---SPLIT---` + 1900 字切塊 → POST webhook，帶**自訂 UA**。webhook 讀序：`WEBHOOK` env → `DISCORD_WEBHOOK_URL` env → 本 repo `.env`（**不讀 alt_killer 的 .env**）
- `discord.yml`：監聽 push 到 `report/**.md` 且 author = bot email → 跑 `post.py`。**預設關**：開頭 `if: ${{ vars.ENABLE_DISCORD_PUSH == 'true' }}`，使用者之後在 repo variables 設 `ENABLE_DISCORD_PUSH=true` 才會發
- 另給**手動路徑**：`workflow_dispatch` 指定 report 手動發 + 本機 `python discord/post.py --report report/2026-06-15/am-brief.md`
- 滿足「接口做好、我之後自己丟」

---

## 10. 前身踩坑解法（直接沿用）

1. Discord 擋預設 urllib UA → **403** ⟹ 帶自訂 `User-Agent`
2. 單訊息 **2000 字**上限 ⟹ 1900 切塊 + `---SPLIT---`
3. CCR sandbox **擋 discord.com**（只放行 github.com / api.github.com）⟹ routine 不直接打 Discord，只寫 repo（主走 Contents API，見 §8），由 GHA 代發 Discord
4. routine 與 fetch workflow **時序/衝突** ⟹ Contents API 是 atomic PUT、無 local merge 問題；若用 git push 備案，push 前 `git fetch + merge`（或 `--autostash`）。anchor 已比 slot 晚 30 分，時間錯開
5. GHA cron **不精準**（±5–15 min lag）⟹ 數據抓取可接受 lag；analysis 用 Anthropic routine（較準）+ generated_at 檢查。**這是取捨**：換來全 cloud 零本機，符合 Mac 移植優先
6. RSS/翻譯 best-effort ⟹ 單源失敗只記 `errors[]` 不中斷
7. yfinance fund holdings 可能 flaky ⟹ ETF 發行商 holdings 檔 fallback（`XL*` 走 SSGA、`SOXX` 走 iShares，見 §3）
8. **routine 寫檔認證**：前身死在 routine `git push` 連續 HTTP 403（root cause 未定論）。本版**主走 GitHub Contents API**（避開 git credential）；git push 僅在 smoke test 證明可行才用。先 1 個 routine 證明能寫進 repo 再 scale（見 §8）

---

## 11. 依賴 + 跨平台 + 資料保留

- `requirements.txt`：`yfinance feedparser exchange-calendars requests deep-translator pandas openpyxl`
- 全 cloud（GHA + Anthropic routine + GitHub Pages），筆電關機照跑
- Mac 移植：重登 claude.ai（routine 不受影響）+ `git clone twus-daily` + webhook secret 在 GHA，近乎零成本
- 所有路徑 `pathlib`，不 hardcode home
- **資料保留**：`data/` 只留 90 天，舊的由 `fetch.yml`（或獨立 cleanup workflow）刪除或歸到 `archive` 分支，避免 main 無限膨脹 + Pages rebuild 變慢

---

## 12. Codex 動工順序（建議）

1. **spike TWSE 台股股數來源**（§3）——先解這個唯一結構性風險，再寫其他
2. 建 repo `twus-daily`（public）+ 目錄骨架 + requirements
3. 寫 `fetch/`（sources → universe → snapshot），先跑通一個 slot 產出合 schema 的 JSON
4. 寫 `site/` dashboard，吃 JSON 渲染
5. 設 `fetch.yml` cron（5 slot）+ `pages.yml` 部署
6. 建 `am-brief` 一個 routine，**write smoke test**（§8），通過才開另兩個
7. 寫 `discord/post.py` + `discord.yml`（預設 off）
8. holiday filter + data 保留策略收尾

---

## 附錄：Pre-mortem（動工前要驗的點，按致命度排序）

1. **台股股數來源**（§3）：市值前十排不出來 = 整套卡死。Codex 第一步 spike。
2. **routine 寫檔路徑**（§8）：前身死在 routine `git push` HTTP 403。先用 1 個 routine 以 Contents API 證明能寫進 repo，再 scale；**不要預設 git push 會通**。
3. **fetch/analysis race**（§5）：anchor 晚 30 分 + generated_at 檢查雙保險；驗證早報真的讀到當日 tw-pre。
4. **GHA cron lag 對盤前報告**：08:30 早報能否容忍 lag 到 ~08:45。不行才考慮備援 trigger（會破壞全 cloud，最後手段）。
5. **yfinance 抓台股 `.TW` 即時性**：盤中 slot 台股報價 yfinance 延遲 ~15–20 分；盤前/盤後影響小，盤中要即時得走 TWSE API。
