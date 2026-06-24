# twus-daily — 即時刷新 Worker 設定教學

這個 Cloudflare Worker 是 dashboard「現在去抓」功能的中繼站。  
它幫你保管 GitHub token，收到請求後就去觸發 GitHub Actions 抓資料。  
**token 只放在 Cloudflare，不會出現在公開網頁。**

---

## 步驟 1 — 建立 GitHub Fine-grained PAT

1. 登入 GitHub → 右上角頭像 → **Settings**
2. 左側欄滑到最下面 → **Developer settings**
3. **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
4. 設定：
   - **Token name**：隨意取（如 `twus-refresh-worker`）
   - **Expiration**：建議選 1 年
   - **Repository access** → 選 **Only select repositories** → 選 `twus-daily`
   - **Permissions** → 找 **Actions** → 設為 **Read and write**
   - 其他 Permissions 保持 No access
5. 按 **Generate token**，畫面出現一串 `github_pat_...` 開頭的字串
6. **立刻複製並暫存**（離開頁面就看不到了）

---

## 步驟 2 — 建立 Cloudflare Worker

> 免費帳號就夠用，每天 10 萬次請求免費額度對個人用完全不會超。

1. 前往 [cloudflare.com](https://cloudflare.com) 註冊或登入
2. 左側選單 → **Workers & Pages**
3. 右上角 **Create** → **Create Worker**
4. **命名**：輸入 `twus-refresh`（或任意名稱），下面的名稱決定 Worker 網址
5. 按 **Deploy**（先部署一個空殼，等下再貼程式碼）
6. 部署完成後按 **Edit code**
7. 把 `worker/fetch-trigger.js` 的**所有內容**貼進編輯器，取代原本的 Hello World
8. 按右上角 **Deploy** 部署

---

## 步驟 3 — 設定 Secret（存 GitHub token）

1. 在剛才的 Worker 頁面，點上方 **Settings** 分頁
2. 左側 **Variables and Secrets** → **Add** → 選 **Secret**
3. **Variable name**：填 `GH_PAT`（大寫，一字不差）
4. **Value**：貼上步驟 1 複製的 token（`github_pat_...`）
5. 按 **Save and deploy**

> **注意**：Secret 設定後不會再顯示明文，如果忘記就重新在 GitHub 產一個新的，再來這裡更新。

---

## 步驟 4 — 複製 Worker 網址

1. Worker 頁面右上角或 Settings 頁面都能看到網址，格式為：  
   `https://twus-refresh.你的帳號.workers.dev`
2. 複製這個網址

---

## 步驟 5 — 把網址交給 Claude

把上面的 Worker 網址**直接貼給 Claude**，讓 Claude 填進 `site/app.js` 的 `REFRESH_WORKER_URL` 常數。

**不要把 GitHub token 傳給 Claude 或貼到任何公開地方。**  
Token 只放在 Cloudflare Worker Secret，那是唯一安全的地方。

---

## 驗證是否正常

設定完成後，到 dashboard 點「🔄 刷新」：

- 按鈕會變成「⏳ 抓取中…（約 2 分鐘）」
- 約 1–3 分鐘後 GitHub Actions 跑完，dashboard 自動更新
- 按鈕恢復並短暫顯示「✓ 已更新」

如果卡住或逾時，先到 GitHub repo 的 **Actions** 頁面確認 workflow 有沒有被觸發。

---

## 常見問題

**Q：每次點刷新都要等 2 分鐘？**  
A：是的，因為 GitHub Actions 要花時間跑（抓資料、寫 JSON、push 回 repo）。這個功能是「叫 GitHub 現在去抓」，不是瞬間完成的。

**Q：我同時按兩次刷新會發生什麼事？**  
A：按鈕在等待期間是 disabled，所以不會重複觸發。

**Q：Worker 會不會被別人亂用？**  
A：Worker URL 是公開的，任何人都能 POST 觸發你的 workflow。要加防護的話，可以在 Worker 加一個簡單的 secret header 驗證，但對個人 dashboard 來說通常不需要。
