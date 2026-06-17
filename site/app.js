/* =====================================================
   twus-daily dashboard — app.js
   純 vanilla JS，無框架，無 build step
   ===================================================== */

/* ── 常數 ── */
const SLOTS = ['tw-pre', 'tw-mid', 'tw-close', 'us-pre', 'us-mid'];
const ANCHORS = ['am-brief', 'tw-wrap', 'us-preview'];

/* 狀態燈標籤 */
const STATUS_LABELS = {
  pre:     '盤前',
  open:    '盤中',
  closed:  '收盤',
  holiday: '休市',
};

/* 風險情緒燈門檻（VIX）
   - VIX < 15 → 低風險（綠）
   - 15 ≤ VIX < 25 → 中風險（黃）
   - VIX ≥ 25 → 高風險（紅）
*/
function vixRiskLevel(vix) {
  if (vix === null || vix === undefined) return 'mid';
  if (vix < 15)  return 'low';
  if (vix < 25)  return 'mid';
  return 'high';
}

const RISK_LABEL = { low: '低風險', mid: '中風險', high: '高風險' };

/* ── 應用程式狀態 ── */
const state = {
  date:   null,   // YYYY-MM-DD
  slot:   null,   // 目前選中的 slot
  anchor: 'am-brief',
  data:   null,   // 目前載入的 snapshot JSON
};

/* ── 工具函式 ── */

/** 安全格式化數值；null/undefined/NaN → '—' */
function fmt(v, digits = 2) {
  if (v === null || v === undefined || (typeof v === 'number' && isNaN(v))) return '—';
  return Number(v).toFixed(digits);
}

/** 格式化漲跌幅（帶 +/- 符號） */
function fmtPct(v, digits = 2) {
  if (v === null || v === undefined || (typeof v === 'number' && isNaN(v))) return '—';
  const n = Number(v);
  return (n >= 0 ? '+' : '') + n.toFixed(digits) + '%';
}

/** 根據漲跌幅回傳 CSS class（台股慣例：紅漲綠跌） */
function pctClass(v) {
  if (v === null || v === undefined || isNaN(v)) return 'text-flat';
  return v > 0 ? 'text-up' : v < 0 ? 'text-down' : 'text-flat';
}

/** 將 change_pct 轉成熱力圖背景色
    台股慣例：紅漲（正值）/ 綠跌（負值）
    強度：0%→透明灰、±5% 以上飽和 */
function heatColor(pct) {
  if (pct === null || pct === undefined || isNaN(pct)) {
    return 'background: #1c2129; color: #8b949e;';
  }
  const v = Number(pct);
  const intensity = Math.min(Math.abs(v) / 5, 1);  // 5% 以上為最深色
  if (v > 0) {
    // 上漲 → 紅系
    const r = Math.round(100 + 148 * intensity);
    const g = Math.round(20  + 30  * (1 - intensity));
    const b = Math.round(20  + 30  * (1 - intensity));
    return `background: rgb(${r},${g},${b}); color: #fff;`;
  } else if (v < 0) {
    // 下跌 → 綠系
    const r = Math.round(20  + 30  * (1 - intensity));
    const g = Math.round(80  + 105 * intensity);
    const b = Math.round(40  + 60  * (1 - intensity));
    return `background: rgb(${r},${g},${b}); color: #fff;`;
  }
  return 'background: #2d333b; color: #8b949e;';
}

/** 格式化 ISO datetime → 易讀字串 */
function fmtDatetime(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString('zh-TW', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
      hour12: false,
    });
  } catch { return iso; }
}

/* ── 路徑前綴偵測
   GitHub Pages 上 site/ 的內容被打平到 repo 根，所以路徑是 ./data/、./report/。
   本地開發若從 site/ 目錄 serve（URL 含 /site/），則 data/ 和 report/ 在上一層，
   需要用 ../data/、../report/。
   ── */
const DATA_PREFIX = window.location.pathname.includes('/site/')
  ? '../data/'
  : './data/';
const REPORT_PREFIX = window.location.pathname.includes('/site/')
  ? '../report/'
  : './report/';

/* ── 資料載入 ── */

/** 載入指定 date + slot 的 snapshot JSON */
async function loadSnapshot(date, slot) {
  const url = slot === 'latest'
    ? `${DATA_PREFIX}latest.json`
    : `${DATA_PREFIX}${date}/${slot}.json`;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error('[loadSnapshot]', url, e);
    return null;
  }
}

/** 載入 report markdown */
async function loadReport(date, anchor) {
  const url = `${REPORT_PREFIX}${date}/${anchor}.md`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } catch (e) {
    console.warn('[loadReport]', url, e);
    return null;
  }
}

/* ── 渲染：Header ── */
function renderHeader(data) {
  /* 交易日 */
  document.getElementById('trading-day').textContent = data.trading_day || '—';

  /* 狀態燈 */
  ['tw', 'us'].forEach(mkt => {
    const status = data.market_status?.[mkt] || 'closed';
    const dot   = document.getElementById(`${mkt}-status-dot`);
    const label = document.getElementById(`${mkt}-status-label`);
    dot.className   = `status-dot ${status}`;
    const mktName   = mkt === 'tw' ? '台股' : '美股';
    label.textContent = `${mktName} ${STATUS_LABELS[status] || status}`;
  });

  /* 資料時間戳 */
  document.getElementById('data-timestamp').textContent =
    data.generated_at ? `資料時間 ${fmtDatetime(data.generated_at)}` : '';

  /* 錯誤旗標 */
  const errFlag = document.getElementById('error-flag');
  if (data.errors && data.errors.length > 0) {
    errFlag.style.display = 'inline';
  } else {
    errFlag.style.display = 'none';
  }
}

/* ── 渲染：§2 當日最強卡 ── */
function renderHighlights(data) {
  const hl = data.highlights || {};

  /* 最強板塊 */
  const ss = hl.strongest_sector;
  const nameEl = document.getElementById('hl-sector-name');
  const pctEl  = document.getElementById('hl-sector-pct');
  const regEl  = document.getElementById('hl-sector-region');
  if (ss) {
    nameEl.textContent = ss.sector || '—';
    pctEl.textContent  = fmtPct(ss.change_pct);
    pctEl.className    = `strongest-pct ${pctClass(ss.change_pct)}`;
    regEl.textContent  = ss.region === 'US' ? '美股' : '台股';
  } else {
    nameEl.textContent = '—';
    pctEl.textContent  = '—';
    regEl.textContent  = '';
  }

  /* 板塊領漲 */
  const leaders = document.getElementById('hl-leaders');
  leaders.innerHTML = '';
  (hl.sector_leaders || []).slice(0, 5).forEach(item => {
    const li = document.createElement('li');
    li.className = 'leader-item';
    li.innerHTML = `
      <span class="font-bold">${escHtml(item.symbol)}</span>
      <span class="${pctClass(item.change_pct)}">${fmtPct(item.change_pct)}</span>`;
    leaders.appendChild(li);
  });
  if (!(hl.sector_leaders?.length)) leaders.innerHTML = '<li style="color:var(--text-muted)">—</li>';

  /* 題材股（top_gainers） */
  const gainers = document.getElementById('hl-gainers');
  gainers.innerHTML = '';
  (hl.top_gainers || []).slice(0, 4).forEach(item => {
    const li = document.createElement('li');
    li.className = 'mover-item';
    li.innerHTML = `
      <span>
        <span class="font-bold">${escHtml(item.symbol)}</span>
        <span class="mover-note">${escHtml(item.note || item.name || '')}</span>
      </span>
      <span class="${pctClass(item.change_pct)}">${fmtPct(item.change_pct)}</span>`;
    gainers.appendChild(li);
  });
  if (!(hl.top_gainers?.length)) gainers.innerHTML = '<li style="color:var(--text-muted)">—</li>';
}

/* ── 渲染：§3 指數區 ── */
function renderIndices(data) {
  const indices = data.indices || [];

  /* 依 region 分組 */
  const groups = { TW: [], US: [], INTL: [] };
  indices.forEach(q => {
    const r = q.region || 'INTL';
    if (groups[r]) groups[r].push(q);
  });

  /* 各 region 渲染 */
  ['TW', 'US', 'INTL'].forEach(region => {
    const container = document.getElementById(`indices-${region}`);
    container.innerHTML = '';
    groups[region].forEach(q => {
      const card = document.createElement('div');
      card.className = 'index-card';
      card.innerHTML = `
        <div class="index-symbol">${escHtml(q.symbol)}</div>
        <div class="index-name">${escHtml(q.name)}</div>
        <div class="index-price">${q.price !== null && q.price !== undefined ? fmt(q.price) : '<span class="null-val">—</span>'}</div>
        <div class="index-change ${pctClass(q.change_pct)}">
          ${q.change !== null && q.change !== undefined ? (q.change >= 0 ? '+' : '') + fmt(q.change) : '—'}
          &nbsp;(${fmtPct(q.change_pct)})
        </div>`;
      container.appendChild(card);
    });
    if (!groups[region].length) {
      container.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem">暫無資料</div>';
    }
  });

  /* 期貨（顯示在美股 panel 下方） */
  const futuresList = document.getElementById('futures-list');
  futuresList.innerHTML = '';
  const futures = data.macro?.futures || [];
  futures.forEach(f => {
    const chip = document.createElement('div');
    chip.className = `futures-chip ${pctClass(f.change_pct)}`;
    chip.innerHTML = `${escHtml(f.name || f.symbol)} <span class="${pctClass(f.change_pct)}">${fmtPct(f.change_pct)}</span>`;
    futuresList.appendChild(chip);
  });
}

/* ── 渲染：§4 Macro 區 ── */
function renderMacro(data) {
  const macro = data.macro || {};
  const grid  = document.getElementById('macro-grid');
  grid.innerHTML = '';

  /* VIX */
  if (macro.vix !== null && macro.vix !== undefined) {
    const risk  = vixRiskLevel(macro.vix?.value);
    const card  = makeMacroCard({
      label:  'VIX 恐慌指數',
      value:  fmt(macro.vix?.value, 2),
      change: `${fmtPct(macro.vix?.change_pct)} 昨日`,
      changeCls: pctClass(macro.vix?.change_pct),
      extra: `<div class="risk-light ${risk}">● ${RISK_LABEL[risk]}</div>`,
    });
    grid.appendChild(card);
  }

  /* 10Y 殖利率 */
  if (macro.us10y !== null && macro.us10y !== undefined) {
    const bps    = macro.us10y?.change_bps;
    const bpsStr = bps !== null && bps !== undefined ? (bps >= 0 ? '+' : '') + bps + ' bps' : '—';
    const card   = makeMacroCard({
      label:  '美10Y殖利率',
      value:  macro.us10y?.value !== null && macro.us10y?.value !== undefined ? fmt(macro.us10y.value, 2) + '%' : '—',
      change: bpsStr,
      changeCls: bps > 0 ? 'text-up' : bps < 0 ? 'text-down' : 'text-flat',
    });
    grid.appendChild(card);
  }

  /* 30Y 殖利率 */
  if (macro.us30y !== null && macro.us30y !== undefined) {
    const bps    = macro.us30y?.change_bps;
    const bpsStr = bps !== null && bps !== undefined ? (bps >= 0 ? '+' : '') + bps + ' bps' : '—';
    const card   = makeMacroCard({
      label:  '美30Y殖利率',
      value:  macro.us30y?.value !== null && macro.us30y?.value !== undefined ? fmt(macro.us30y.value, 2) + '%' : '—',
      change: bpsStr,
      changeCls: bps > 0 ? 'text-up' : bps < 0 ? 'text-down' : 'text-flat',
    });
    grid.appendChild(card);
  }

  /* DXY */
  if (macro.dxy !== null && macro.dxy !== undefined) {
    const card = makeMacroCard({
      label:  '美元指數 DXY',
      value:  fmt(macro.dxy?.value, 2),
      change: `${fmtPct(macro.dxy?.change_pct)} 昨日`,
      changeCls: pctClass(macro.dxy?.change_pct),
    });
    grid.appendChild(card);
  }

  /* 若 macro 全空 */
  if (!grid.children.length) {
    grid.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem">暫無 Macro 資料</div>';
  }
}

/** 建立單一 macro 卡 DOM */
function makeMacroCard({ label, value, change, changeCls, extra = '' }) {
  const card = document.createElement('div');
  card.className = 'macro-card';
  card.innerHTML = `
    <div class="macro-label">${escHtml(label)}</div>
    <div class="macro-value">${value !== '—' ? escHtml(value) : '<span class="null-val">—</span>'}</div>
    <div class="macro-change ${changeCls || ''}">${escHtml(change)}</div>
    ${extra}`;
  return card;
}

/* ── 渲染：§5 板塊熱力圖 ── */
function renderSectors(data) {
  renderHeatmap(data.sectors?.US || [], 'US');
  renderHeatmap(data.sectors?.TW || [], 'TW');
}

function renderHeatmap(sectors, market) {
  const grid = document.getElementById(`heatmap-${market}`);
  grid.innerHTML = '';

  sectors.forEach((sec, idx) => {
    /* 色塊 */
    const block = document.createElement('div');
    block.className = 'sector-block';
    block.style.cssText = heatColor(sec.change_pct);
    block.dataset.idx = idx;

    const etfTag = sec.etf
      ? `<div class="sector-block-etf">${escHtml(sec.etf)}</div>`
      : '';
    block.innerHTML = `
      <div class="sector-block-name">${escHtml(sec.sector)}</div>
      ${etfTag}
      <div class="sector-block-pct">${fmtPct(sec.change_pct)}</div>`;

    /* 成分股展開面板 */
    const panel = document.createElement('div');
    panel.className = 'sector-constituents';
    panel.id = `const-${market}-${idx}`;

    const constituents = sec.constituents || [];
    if (constituents.length) {
      panel.innerHTML = constituents.map(c => `
        <div class="constituent-row">
          <div>
            <span class="constituent-symbol">${escHtml(c.symbol)}</span>
            <span class="constituent-name">${escHtml(c.name || '')}</span>
          </div>
          <span class="constituent-pct ${pctClass(c.change_pct)}">${fmtPct(c.change_pct)}</span>
        </div>`).join('');
    } else {
      panel.innerHTML = '<div style="color:var(--text-muted);font-size:0.82rem">無成分股資料</div>';
    }

    /* 點選切換展開 */
    block.addEventListener('click', () => {
      const isOpen = panel.classList.contains('open');
      /* 收起同 market 所有已展開的面板 */
      grid.querySelectorAll('.sector-constituents.open').forEach(p => {
        p.classList.remove('open');
        p.previousElementSibling?.classList.remove('expanded');
      });
      if (!isOpen) {
        panel.classList.add('open');
        block.classList.add('expanded');
      }
    });

    grid.appendChild(block);
    grid.appendChild(panel);
  });

  if (!sectors.length) {
    grid.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem">暫無板塊資料</div>';
  }
}

/* ── 渲染：§6 加密小區 ── */
function renderCrypto(data) {
  const grid  = document.getElementById('crypto-grid');
  const items = data.crypto || [];
  grid.innerHTML = '';

  items.forEach(c => {
    const card = document.createElement('div');
    card.className = 'crypto-card';
    card.innerHTML = `
      <div class="crypto-symbol">${escHtml(c.symbol)}</div>
      <div class="crypto-price">${c.price !== null && c.price !== undefined ? '$' + Number(c.price).toLocaleString('en-US', {maximumFractionDigits: 2}) : '<span class="null-val">—</span>'}</div>
      <div class="crypto-change ${pctClass(c.change_pct_24h)}">24h ${fmtPct(c.change_pct_24h)}</div>`;
    grid.appendChild(card);
  });

  if (!items.length) {
    grid.innerHTML = '<div class="card" style="color:var(--text-muted);font-size:0.85rem">暫無加密貨幣資料</div>';
  }
}

/* ── 渲染：§7 新聞流 ── */
function renderNews(data) {
  const news    = data.news || [];
  const filter  = document.getElementById('news-filter');
  const list    = document.getElementById('news-list');

  /* 收集所有 tag */
  const tags = ['全部', ...new Set(news.map(n => n.tag || '其他').filter(Boolean))];

  /* 建立 tag 過濾按鈕 */
  filter.innerHTML = '';
  let activeTag = '全部';

  tags.forEach(tag => {
    const btn = document.createElement('button');
    btn.className = `news-tag-btn${tag === '全部' ? ' active' : ''}`;
    btn.textContent = tag;
    btn.addEventListener('click', () => {
      filter.querySelectorAll('.news-tag-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeTag = tag;
      renderNewsList(news, activeTag, list);
    });
    filter.appendChild(btn);
  });

  renderNewsList(news, activeTag, list);
}

function renderNewsList(news, activeTag, list) {
  const filtered = activeTag === '全部'
    ? news
    : news.filter(n => (n.tag || '其他') === activeTag);

  list.innerHTML = '';
  filtered.forEach(n => {
    const item = document.createElement('div');
    item.className = 'news-item';

    const pubStr = n.published ? fmtDatetime(n.published) : '';
    const transLabel = n.translated ? '<span class="news-translated">AI 翻譯</span>' : '';

    item.innerHTML = `
      <div class="news-meta">
        <span class="news-tag-badge">${escHtml(n.tag || '')}</span>
        <span>${escHtml(n.source || '')}</span>
        ${pubStr ? `<span>${escHtml(pubStr)}</span>` : ''}
        ${transLabel}
      </div>
      <div class="news-title">
        <a href="${escAttr(n.url || '#')}" target="_blank" rel="noopener">${escHtml(n.title)}</a>
      </div>
      ${n.summary ? `<div class="news-summary">${escHtml(n.summary)}</div>` : ''}`;
    list.appendChild(item);
  });

  if (!filtered.length) {
    list.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem;padding:12px 0">無相關新聞</div>';
  }
}

/* ── 渲染：§8 分析報告區 ── */
async function renderReport(date, anchor) {
  const content = document.getElementById('report-content');
  const loading = document.getElementById('report-loading');

  content.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem;padding:20px 0;text-align:center"><span class="spinner"></span>&nbsp;載入中…</div>';
  loading.style.display = 'inline';

  const md = await loadReport(date, anchor);
  loading.style.display = 'none';

  if (md === null) {
    content.innerHTML = '<div style="color:var(--text-muted);font-size:0.85rem;padding:16px 0">本時段報告尚未產生，或歷史資料不存在。</div>';
    return;
  }

  /* 用 marked.js 渲染 markdown（去掉 ---SPLIT--- 分隔符） */
  const cleaned = md.replace(/---SPLIT---/g, '\n\n---\n\n');
  content.innerHTML = marked.parse(cleaned);
}

/* ── 渲染：errors footer ── */
function renderErrors(data) {
  const errors  = data.errors || [];
  const footer  = document.getElementById('errors-footer');
  const errList = document.getElementById('errors-list');

  if (!errors.length) {
    footer.style.display = 'none';
    return;
  }

  footer.style.display = 'block';
  errList.innerHTML = errors.map(e => `
    <div class="error-row">
      <span class="error-source">[${escHtml(e.stage || '')}] ${escHtml(e.source || '')}</span>
      <span>${escHtml(e.message || '')}</span>
    </div>`).join('');
}

/* ── 主渲染函式 ── */
function renderAll(data) {
  state.data = data;
  renderHeader(data);
  renderHighlights(data);
  renderIndices(data);
  renderMacro(data);
  renderSectors(data);
  renderCrypto(data);
  renderNews(data);
  renderErrors(data);
  /* 報告區讀目前 anchor */
  renderReport(state.date, state.anchor);
}

/* ── 資料切換：slot / date ── */
async function switchTo(date, slot) {
  state.date = date;
  state.slot = slot;

  /* 標記 active slot btn */
  document.querySelectorAll('.slot-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.slot === slot);
  });

  const data = await loadSnapshot(date, slot);
  if (!data) {
    showLoadError();
    return;
  }

  /* 若 JSON 有記錄 trading_day，日期 picker 同步 */
  if (data.trading_day) {
    document.getElementById('date-picker').value = data.trading_day;
    state.date = data.trading_day;
  }

  renderAll(data);
}

function showLoadError() {
  document.getElementById('report-content').innerHTML =
    '<div style="color:var(--color-up);padding:20px">⚠ 資料載入失敗，請確認日期或 slot 是否有效。</div>';
}

/* ── XSS 防護：escHtml / escAttr ── */
function escHtml(str) {
  if (typeof str !== 'string') str = String(str ?? '');
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escAttr(str) {
  return escHtml(str);
}

/* ── 事件綁定 ── */
function bindEvents() {
  /* Slot 切換按鈕 */
  document.querySelectorAll('.slot-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      switchTo(state.date, btn.dataset.slot);
    });
  });

  /* 歷史日期 picker */
  document.getElementById('date-picker').addEventListener('change', e => {
    const newDate = e.target.value;  // YYYY-MM-DD
    if (newDate) switchTo(newDate, state.slot || 'tw-pre');
  });

  /* 指數 tab（台股/美股/國際） */
  document.querySelectorAll('#indices-section .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#indices-section .tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.indices-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`panel-${btn.dataset.region}`).classList.add('active');
    });
  });

  /* 板塊熱力圖 tab（美股/台股） */
  document.querySelectorAll('#sectors-section .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#sectors-section .tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const mkt = btn.dataset.market;
      document.getElementById('heatmap-US').style.display = mkt === 'US' ? 'grid' : 'none';
      document.getElementById('heatmap-TW').style.display = mkt === 'TW' ? 'grid' : 'none';
    });
  });

  /* 報告切換 */
  document.querySelectorAll('.report-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.report-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.anchor = btn.dataset.anchor;
      renderReport(state.date, state.anchor);
    });
  });
}

/* ── 取得今日日期（台灣時間 UTC+8） ── */
function todayTW() {
  const now = new Date();
  /* 轉成 UTC+8 */
  const tw  = new Date(now.getTime() + 8 * 60 * 60 * 1000);
  return tw.toISOString().slice(0, 10);  // YYYY-MM-DD
}

/* ── 初始化 ── */
async function init() {
  bindEvents();

  /* 預設日期為今天（台灣時間） */
  const today = todayTW();
  document.getElementById('date-picker').value = today;
  state.date   = today;
  state.slot   = 'tw-pre';  /* 預設 slot */
  state.anchor = 'am-brief';

  /* 載入 latest.json（首頁預設） */
  const data = await loadSnapshot(today, 'latest');
  if (data) {
    /* 若 latest.json 裡有 slot，高亮對應按鈕 */
    if (data.slot) {
      state.slot = data.slot;
    }
    /* 若 trading_day 不是今天（如假日後首個工作日），更新 state.date */
    if (data.trading_day) {
      state.date = data.trading_day;
      document.getElementById('date-picker').value = data.trading_day;
    }
    document.querySelectorAll('.slot-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.slot === state.slot);
    });
    renderAll(data);
  } else {
    /* latest.json 不存在時 fallback：嘗試 tw-pre */
    showLoadError();
  }
}

/* 頁面載入完畢後啟動 */
document.addEventListener('DOMContentLoaded', init);
