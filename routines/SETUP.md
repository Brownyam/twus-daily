# 分析層 Routine 設定（claude.ai 網頁）

分析層 = 3 個 cloud routine，定時讀 `data/` 的 JSON、寫整體分析到 `report/`。
本檔給你在 **claude.ai 的 routine / 排程介面**手動建立（routine API 已換 v2 schema，不從本機 API 盲建）。

> **安全**：routine 要把報告寫回 GitHub，需要 GitHub 寫入權限。**先用「不帶 PAT」測**（下方 prompt 第一次跑會自我診斷環境現成的認證夠不夠）。若回報 401/403，再依「PAT 備援」加一個 token。**Claude 不經手 token，放 token 這步由你做。**

---

## 步驟（先建 am-brief 一個，通了再建另兩個）

1. 在 claude.ai 開一個新的 routine / scheduled task。
2. **連結 repo**：`Brownyam/twus-daily`（GitHub App「Claude」已是 All repositories，應該直接可選）。
3. **貼 prompt**：用下面 `am-brief` 的 prompt 區塊。
4. **排程**：平日 08:30（台北時間）。對應其他 anchor：tw-wrap 14:15、us-preview 21:30。
5. **Model**：Opus 4.8（配額吃緊可改 Sonnet 4.6）。
6. 存檔後**手動跑一次**，看 routine 回報的「認證診斷 + 寫檔結果」：
   - ✅ 成功寫進 `report/{今日}/am-brief.md` → 不用 PAT，直接建另兩個 routine。
   - ❌ 401/403 → 走下方「PAT 備援」。

---

## am-brief routine prompt（複製貼上）

```
你是台美股財經分析助手，並負責把報告寫回 GitHub repo Brownyam/twus-daily（本 routine 已連此 repo）。

## 任務
1. 算出「今日」台灣日期（UTC+8），記為 TODAY（YYYY-MM-DD）。
2. 抓最新數據：curl -s https://raw.githubusercontent.com/Brownyam/twus-daily/main/data/latest.json
   檢查 JSON 的 generated_at 是否為今天（UTC+8）；不是 → 報告開頭標「資料非當日，僅供參考」。
3. 寫「🌅 早報」分析（繁中、先結論、結尾不加致謝語），結構：
   ① 一句結論 ② 關鍵數字（台股加權/期指、美股四大+費半、VIX/10Y·30Y殖利率/DXY、美股期貨）
   ③ 板塊輪動 + 當日最強題材 ④ 日內判斷與情境 ⑤ 關注標的 ⑥ 風險提示
   段落之間用 ---SPLIT--- 分隔。

## 寫檔（含認證自我診斷——第一次跑請完整回報）
a. 先診斷環境有什麼 GitHub 認證（只看有沒有，不要印出 token 值）：
   env | grep -iE 'github|gh_|token' | sed 's/=.*/=<redacted>/'
   gh auth status 2>&1
b. 把報告內容 base64，寫到 report/TODAY/am-brief.md（GitHub Contents API）：
   - 若 gh 可用，最簡單：
     gh api --method PUT repos/Brownyam/twus-daily/contents/report/TODAY/am-brief.md \
       -f message="report: am-brief TODAY" -f branch=main \
       -f committer[name]=daily-report-bot -f committer[email]=daily-report-bot@users.noreply.github.com \
       -f content="<base64>"
   - 若該路徑已存在，先 GET 拿 sha 帶 -f sha=<sha>（更新）；不存在就不帶 sha（新建）。
   - 若無 gh，改用 curl PUT api.github.com，Authorization 用環境裡能找到的 GitHub 認證。
c. 明確回報：用了哪種認證、HTTP status、成功或失敗。若 401/403，貼出錯誤訊息後停止（代表環境無寫入權限，需改用注入的 PAT），不要重試。

## 限制
只寫 report/TODAY/am-brief.md 這一個檔，不要動 repo 其他東西。
```

> tw-wrap / us-preview 兩個 routine：把上面標題與 slot 換掉即可——
> - **tw-wrap**（🏁 台股收盤，14:15）：讀 `data/{TODAY}/tw-close.json`，寫 `report/TODAY/tw-wrap.md`，內容＝台股當天總結 + 板塊輪動。
> - **us-preview**（🌃 美股盤前，21:30）：讀 `data/{TODAY}/us-pre.json`，寫 `report/TODAY/us-preview.md`，內容＝展望美股當夜 + 關注標的。

---

## PAT 備援（只有上面回報 401/403 才需要）

1. 你建一個 **fine-grained PAT**：GitHub → Settings → Developer settings → Fine-grained tokens → Generate
   - Resource owner：Brownyam｜Repository access：Only select → **twus-daily**
   - Permissions → Repository → **Contents: Read and write**（只要這一個）
   - 到期日設短一點（會過期，過期要換）
2. 在 routine 的 secret / 環境變數設定把它放成 `GITHUB_TOKEN`（**你親手放，Claude 不碰 token**）。若介面要設 networking allowlist，加 `api.github.com`。
3. prompt 的寫檔改成帶 `Authorization: Bearer $GITHUB_TOKEN` 打 Contents API。

---

## 上線後

- 3 個 routine 寫的 `report/*.md` push 進 repo → 會觸發 `pages.yml` 部署 → dashboard 的「分析報告」區就有內容。
  （注意：若 routine 用 GitHub App token push 而非 GITHUB_TOKEN，pages 會正常觸發；若不觸發，比照 fetch.yml 在寫檔後加一個 dispatch。）
- 要 Discord 推送：repo Settings → Secrets 設 `DISCORD_WEBHOOK_URL`、Variables 設 `ENABLE_DISCORD_PUSH=true`。
