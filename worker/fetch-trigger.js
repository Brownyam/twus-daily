/**
 * fetch-trigger.js — Cloudflare Worker
 *
 * 功能：收到 POST 請求後，透過 GitHub API 觸發 fetch.yml workflow_dispatch，
 *       讓 dashboard 可即時抓取新資料，而不用等排程。
 *
 * 環境變數（Cloudflare Secret，不寫死在程式）：
 *   GH_PAT  — GitHub Fine-grained PAT，授權 twus-daily repo 的 Actions: Read and write
 */

/* 允許的 slot 值（與 fetch.yml input 對應） */
const VALID_SLOTS = ['tw-pre', 'tw-mid', 'tw-close', 'us-pre', 'us-mid'];

/* GitHub API endpoint */
const GITHUB_DISPATCH_URL =
  'https://api.github.com/repos/Brownyam/twus-daily/actions/workflows/fetch.yml/dispatches';

/* 共用 CORS headers — 允許 GitHub Pages 或任何來源呼叫 */
const CORS_HEADERS = {
  'Access-Control-Allow-Origin':  '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export default {
  /**
   * 主進入點
   * @param {Request} request
   * @param {object}  env       — Cloudflare Worker 環境（含 Secrets）
   */
  async fetch(request, env) {

    /* ── CORS preflight ── */
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    /* ── 只接受 POST ── */
    if (request.method !== 'POST') {
      return jsonResponse({ ok: false, error: 'Method Not Allowed' }, 405);
    }

    /* ── 解析 slot（query param ?slot=...，不合法就預設 tw-close） ── */
    const url  = new URL(request.url);
    const raw  = url.searchParams.get('slot') || '';
    const slot = VALID_SLOTS.includes(raw) ? raw : 'tw-close';

    /* ── 呼叫 GitHub Actions workflow_dispatch ── */
    let ghRes;
    try {
      ghRes = await fetch(GITHUB_DISPATCH_URL, {
        method: 'POST',
        headers: {
          'Authorization':        `Bearer ${env.GH_PAT}`,
          'Accept':               'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'User-Agent':           'twus-daily-refresh',
          'Content-Type':         'application/json',
        },
        body: JSON.stringify({ ref: 'main', inputs: { slot } }),
      });
    } catch (err) {
      /* 網路層錯誤（罕見） */
      return jsonResponse(
        { ok: false, status: 0, detail: `fetch failed: ${err.message}` },
        502,
      );
    }

    /* ── 解讀 GitHub 回應 ──
         204 No Content = 觸發成功
         其他 = 失敗（403 = PAT 權限不足、404 = workflow 不存在、422 = 參數錯誤）
    */
    if (ghRes.status === 204) {
      return jsonResponse({ ok: true, slot }, 200);
    }

    /* 嘗試讀 GitHub 錯誤訊息文字（有助 debug） */
    let detail = '';
    try { detail = await ghRes.text(); } catch { /* 忽略 */ }

    return jsonResponse(
      { ok: false, status: ghRes.status, detail },
      502,
    );
  },
};

/* ── 工具：JSON 回應（統一帶 CORS headers） ── */
function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...CORS_HEADERS,
      'Content-Type': 'application/json',
    },
  });
}
