# Fetch-in-Routine Viability Test

**Run date:** 2026-06-22  
**Environment:** Claude Code remote routine (ephemeral container)

---

## Step 1 — `git clone`

| Item | Value |
|------|-------|
| Command | `git clone https://github.com/Brownyam/twus-daily.git /tmp/twus` |
| Result | **SUCCESS** |
| Elapsed | ~0 s |
| Notes | Public repo, no auth needed, cloned instantly. |

---

## Step 2 — `pip install -r requirements.txt`

| Item | Value |
|------|-------|
| Command (1st try) | `pip install -r requirements.txt` (bare `pip` = `/usr/bin/pip`, Python 3.11 system) |
| Result | **PARTIAL FAIL** — exited 0 but packages installed to wrong interpreter's site-packages; subsequent `import jsonschema` failed with `ModuleNotFoundError`. |
| Command (2nd try) | `python3 -m pip install -r requirements.txt` |
| Result | **FAIL** (exit 1, ~4 s) — `sgmllib3k` (feedparser dep) could not build wheel. |
| Error | `AttributeError: install_layout` in `/usr/lib/python3/dist-packages/wheel/bdist_wheel.py` — Debian-pinned `wheel 0.42.0` incompatible with current setuptools; cannot upgrade (no RECORD file). |
| Workaround applied | `python3 -m pip install --no-deps feedparser` + manually copied `sgmllib.py` from `sgmllib3k-1.0.0.tar.gz` sdist into `/usr/local/lib/python3.11/dist-packages/`. Then `python3 -m pip install yfinance exchange-calendars deep-translator pandas openpyxl jsonschema`. |
| Final result after workaround | **SUCCESS** (~14 s total). All imports verified OK. |

### Recommendation for requirements.txt / setup script

```bash
# Always use the correct interpreter:
python3 -m pip install --no-deps feedparser
python3 -m pip download --no-deps sgmllib3k -d /tmp/sgml
tar -xzf /tmp/sgml/sgmllib3k-*.tar.gz -C /tmp/sgml
cp /tmp/sgml/sgmllib3k-*/sgmllib.py "$(python3 -c 'import site; print(site.getsitepackages()[0])')/"
python3 -m pip install yfinance exchange-calendars deep-translator pandas openpyxl jsonschema
```

Or pin `feedparser==6.0.8` (last release that did not require `sgmllib3k` as a hard dep).

---

## Step 3 — `python fetch/snapshot.py --slot tw-mid --out-dir /tmp/out`

| Item | Value |
|------|-------|
| Command | `python3 fetch/snapshot.py --slot tw-mid --out-dir /tmp/out` |
| Exit code | **0 (success)** |
| Elapsed | **9 s** |
| Schema validation | **PASSED** |
| `trading_day` | `2026-06-22` |
| `generated_at` | `2026-06-22T13:38:03.015671+08:00` |
| Error count in output | **61** |

### Root cause of all 61 errors — Network egress blocked

Every external host returned `HTTP 403: Host not in allowlist`. The routine container's network egress policy does not permit outbound connections to financial data APIs.

Blocked hosts observed:

| Host / API | Used for |
|---|---|
| `query1.finance.yahoo.com`, `query2.finance.yahoo.com` | All Yahoo Finance / yfinance calls (indices, macro, sectors, crypto fallback) |
| `openapi.twse.com.tw` | TWSE MI_INDEX, STOCK_DAY_ALL, t187ap03_L |
| `api.finmindtrade.com` | FinMind TaiwanStockInfo |
| `api.coingecko.com` | CoinGecko crypto prices |
| `www.ssga.com` | SPDR ETF holdings XLSX |
| `www.ishares.com` | iShares SOXX holdings CSV |
| `api.cnyes.com` | Anue 鉅亨網 news |
| RSS feeds (UDN, CTimes, CNA, CNBC, MarketWatch, Nikkei, CoinDesk, BlockTempo) | News via feedparser |

The script completed and wrote valid (but mostly-null) JSON/MD output because all data-fetch errors are caught and logged; the schema still validates. **No data was actually retrieved.**

---

## Summary

| Step | Status | Elapsed |
|------|--------|---------|
| 1. git clone | ✅ Success | ~0 s |
| 2. pip install | ⚠️ Needs workaround (sgmllib3k wheel broken; bare `pip` targets wrong interpreter) | ~14 s (after workaround) |
| 3. snapshot.py | ✅ Script ran, schema passed — but **all 61 data sources 403-blocked** | 9 s |

### Verdict

**The script itself runs in the routine environment. The blocker is the network egress policy.**  
To make this routine actually fetch live data, the following hosts must be added to the environment's egress allowlist:

```
query1.finance.yahoo.com
query2.finance.yahoo.com
openapi.twse.com.tw
api.finmindtrade.com
api.coingecko.com
www.ssga.com
www.ishares.com
api.cnyes.com
rss.udn.com
money.chinatimes.com
feeds.feedburner.com (CNA)
www.cnbc.com
feeds.marketwatch.com
asia.nikkei.com
www.coindesk.com
www.blocktempo.com
```

See: [Claude Code on the Web — network egress settings](https://code.claude.com/docs/en/claude-code-on-the-web)
