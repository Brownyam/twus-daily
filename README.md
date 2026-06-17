# twus-daily — 每日台美股日報系統 v2

每天自動抓取台股 / 美股盤前中後的板塊、指數、macro 數據與新聞，整合成一個 dashboard 網站，並由 AI 在盤前盤後做整體分析與日內判斷。

## 架構（全 cloud，零本機排程）

```
GitHub Actions cron ──► fetch/snapshot.py（抓報價+新聞）──► data/YYYY-MM-DD/{slot}.json
                                                              │
                                                              ▼
                              GitHub Pages dashboard（site/）讀 JSON 渲染
                                                              ▲
Anthropic cloud routine（3 anchor）──► 讀 JSON 做整體分析 ──► report/YYYY-MM-DD/{anchor}.md
                                                              │
                              （可選）GitHub Actions ──► 推 Discord 摘要（預設 off）
```

- **數據快報層**：5 個 slot（台股盤前/盤中/盤後、美股盤前/盤中），純抓數據，便宜高頻
- **分析層**：3 個 anchor（早報 08:30 / 台股收盤 14:15 / 美股盤前 21:30），AI 整體分析
- **動態 universe**：各板塊市值前十大 + 當日最強題材，不寫死清單

## 目錄

| 路徑 | 作用 |
|---|---|
| `fetch/` | 數據抓取（yfinance / TWSE / CoinGecko / RSS）→ JSON + md |
| `schema/snapshot.schema.json` | 數據契約 |
| `data/` | 各 slot 結構化輸出（網站吃） |
| `report/` | 分析層輸出 |
| `site/` | GitHub Pages 靜態 dashboard |
| `discord/` | Discord 發送模組（預設 off） |
| `.github/workflows/` | fetch cron / pages 部署 / discord 代發 |
| `SPEC.md` | 完整實作規格 |

## 狀態

🚧 建置中。完整規格見 [SPEC.md](SPEC.md)。
