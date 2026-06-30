"""
fetch/config.py
單一設定源：資產清單、新聞源、slot 表、TW 產業代碼對照表。
所有 fetch 模組從這裡讀，不要散落在各檔。
"""

# ──────────────────────────────────────────────
# Slot 表
# ──────────────────────────────────────────────
SLOTS = {
    "tw-pre":   {"label": "台股盤前",  "market": "TW"},
    "tw-mid":   {"label": "台股盤中",  "market": "TW"},
    "tw-close": {"label": "台股盤後",  "market": "TW"},
    "us-pre":   {"label": "美股盤前",  "market": "US"},
    "us-mid":   {"label": "美股盤中",  "market": "US"},
}

# ──────────────────────────────────────────────
# 指數清單
# ──────────────────────────────────────────────
INDICES_T1 = [
    {"symbol": "^TWII",   "name": "加權指數",    "region": "TW"},
    {"symbol": "^GSPC",   "name": "S&P 500",     "region": "US"},
    {"symbol": "^IXIC",   "name": "那斯達克",    "region": "US"},
    {"symbol": "^DJI",    "name": "道瓊工業",    "region": "US"},
    {"symbol": "^NDX",    "name": "那斯達克100",  "region": "US"},
    {"symbol": "^RUT",    "name": "羅素2000",     "region": "US"},
    {"symbol": "^SOX",    "name": "費城半導體",   "region": "US"},
]

INDICES_T2 = [
    {"symbol": "^N225",     "name": "日經225",   "region": "INTL"},
    {"symbol": "^KS11",     "name": "韓國KOSPI", "region": "INTL"},
    {"symbol": "^HSI",      "name": "恆生指數",  "region": "INTL"},
    {"symbol": "000001.SS", "name": "上証綜指",  "region": "INTL"},
    {"symbol": "^GDAXI",    "name": "德國DAX",   "region": "INTL"},
    {"symbol": "^FTSE",     "name": "英國富時",  "region": "INTL"},
]

# ──────────────────────────────────────────────
# Macro 資產
# ──────────────────────────────────────────────
MACRO_SYMBOLS = {
    "vix":   "^VIX",
    "us10y": "^TNX",
    "us30y": "^TYX",
    "dxy":   "DX-Y.NYB",
}

FUTURES = [
    {"symbol": "ES=F",  "name": "標普500期貨"},
    {"symbol": "NQ=F",  "name": "那斯達克期貨"},
    {"symbol": "YM=F",  "name": "道瓊期貨"},
    {"symbol": "RTY=F", "name": "羅素2000期貨"},
]

# ──────────────────────────────────────────────
# 美股板塊 ETF（18 檔）
# SOXX/IBB/ITA/ICLN 是 iShares；SMH 是 VanEck；ARKK 是 ARK；KWEB 是 KraneShares
# fallback holdings 只支援 SSGA（XL*）和 SOXX；其餘走 funds_data，抓不到就空
# ──────────────────────────────────────────────
US_SECTOR_ETFS = [
    # ── SPDR 11 大板塊 ──
    {"etf": "XLK",  "sector": "科技"},
    {"etf": "XLF",  "sector": "金融"},
    {"etf": "XLE",  "sector": "能源"},
    {"etf": "XLV",  "sector": "醫療保健"},
    {"etf": "XLY",  "sector": "非必需消費"},
    {"etf": "XLP",  "sector": "必需消費"},
    {"etf": "XLI",  "sector": "工業"},
    {"etf": "XLU",  "sector": "公用事業"},
    {"etf": "XLB",  "sector": "原材料"},
    {"etf": "XLC",  "sector": "通訊服務"},
    {"etf": "XLRE", "sector": "房地產"},
    # ── 主題 ETF ──
    {"etf": "SOXX", "sector": "半導體 iShares"},   # iShares SOX
    {"etf": "SMH",  "sector": "半導體 VanEck"},    # 含台積電，常見基準
    {"etf": "ARKK", "sector": "ARK 創新"},         # 高 beta 科技/AI
    {"etf": "IBB",  "sector": "生技 iShares"},     # 細分生技（vs XLV 大醫療）
    {"etf": "ITA",  "sector": "國防航太"},         # iShares Defense
    {"etf": "KWEB", "sector": "中國科技"},         # 中概 ADR（BABA/JD/PDD）
    {"etf": "ICLN", "sector": "清潔能源"},         # iShares Global Clean Energy
]

# 每個 ETF 抓前 N 支個股（holdings）
US_SECTOR_TOP_N = 15

# SSGA（XL* 系列）fallback holdings URL template
# 用 {etf_lower} 填充，e.g. xlk
SSGA_HOLDINGS_URL = (
    "https://www.ssga.com/us/en/intermediary/etfs/library-content"
    "/products/fund-data/etfs/us/holdings-daily-us-en-{etf_lower}.xlsx"
)

# iShares（SOXX）fallback holdings URL
ISHARES_SOXX_URL = (
    "https://www.ishares.com/us/products/239705/ISHARES-PHLX-SOX-SEMICONDUCTOR-SECTOR-ETF/1521942788811.ajax"
    "?fileType=csv&fileName=iShares-PHLX-SOX_fund&dataType=fund"
)

# ──────────────────────────────────────────────
# 台股 TWSE/FinMind API URL
# ──────────────────────────────────────────────
# ⚠️ openapi.twse.com.tw 會對雲端共享 IP（GitHub Actions）間歇性節流，回 HTML 封鎖頁
#    （「因為您的連線數過多」），導致 json.loads 報 "Expecting value: line 1 column 1"。
#    主來源一律改走 www.twse.com.tw（同資料、不同基礎設施、實測 GHA 穩定）。
#    openapi 端點保留為備援（_get_twse_json 會在主來源失敗時 fallback）。

# 主來源（www.twse.com.tw，GHA 穩定）
TWSE_STOCK_DAY_CSV_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"  # 回 CSV
TWSE_QFIIS_URL = "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?response=json&selectType=ALLBUT0999"  # 發行股數
TWSE_MI_INDEX_WWW_URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALL"      # tables 結構

# 備援（openapi.twse.com.tw，間歇性可用）
TWSE_STOCK_DAY_OPENAPI_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_MI_INDEX_OPENAPI_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
TWSE_COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"  # 僅 local 重生 shares 備援用

FINMIND_STOCK_INFO_URL = (
    "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"
)

# 台股產業別代碼→中文（t187ap03_L 的「產業別」欄是數字代碼）
# 資料來源：TWSE 公開分類，作為 FinMind 無法取得時的 fallback
TW_INDUSTRY_CODE_MAP = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "07": "化學工業",
    "08": "生技醫療",
    "09": "玻璃陶瓷",
    "10": "造紙工業",
    "11": "鋼鐵工業",
    "12": "橡膠工業",
    "13": "汽車工業",
    "14": "半導體業",
    "15": "電腦及週邊設備業",
    "16": "光電業",
    "17": "通信網路業",
    "18": "電子零組件業",
    "19": "電子通路業",
    "20": "資訊服務業",
    "21": "其他電子業",
    "22": "建材營造",
    "23": "航運業",
    "24": "觀光餐旅",
    "25": "金融保險業",
    "26": "貿易百貨業",
    "27": "油電燃氣業",
    "28": "綜合",
    "29": "其他",
    # 一些常見別名（部分 API 回傳有前導零差異，一並收錄）
    "1": "水泥工業",
    "2": "食品工業",
    "3": "塑膠工業",
    "4": "紡織纖維",
    "5": "電機機械",
    "6": "電器電纜",
    "7": "化學工業",
    "8": "生技醫療",
    "9": "玻璃陶瓷",
}

# ──────────────────────────────────────────────
# 台股 top_gainers/losers 品質過濾門檻
# ──────────────────────────────────────────────

# 成交額最低門檻（元）：預設 5000 萬，過濾雞蛋水餃/無量股
# 成交額 = ClosingPrice × TradeVolume（股數）；STOCK_DAY_ALL 無直接成交額欄位，
# 改用「市值 × 換手率」的代理：min_mktcap + min_turnover_shares 雙重過濾
TW_MOVERS_MIN_MKTCAP = 3e9          # 市值 > 30 億（預設），可在此調整
TW_MOVERS_MIN_TRADE_VALUE = 50e6    # 成交額 > 5000 萬（元），可在此調整

# 非產業 bucket 清單：FinMind industry_category 或 t187ap03_L 產業別可能回傳這些板別名，
# 不是真正的產業分類，計算 strongest_sector 時要排除
TW_NON_INDUSTRY_BUCKETS = {
    "創新板股票",
    "創新板",
    "上市",
    "上市股票",
    "未分類",
    "其他",        # 只保留在 TW_INDUSTRY_CODE_MAP 的 '29' fallback，sector 真實名稱比對時才排除
    "綜合",        # code '28'，不代表產業，不用來當最強板塊
    "臺灣存託憑證",
    "受益憑證",
    "認購（售）權證",
    "特別股",
    "ETF",
    "指數股票型基金",
}

# ──────────────────────────────────────────────
# 加密貨幣
# ──────────────────────────────────────────────
# CoinGecko id → 我們用的 symbol
CRYPTO_COINGECKO = {
    "bitcoin":  "BTC",
    "ethereum": "ETH",
}
CRYPTO_YF_FALLBACK = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
}
COINGECKO_PRICE_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
)

# ──────────────────────────────────────────────
# 新聞源
# tag: 🇹🇼=台灣 🇺🇸=美國 🪙=加密
# translate: True=英文需翻中，False=中文直接用
# kind: "rss" | "json_api"
# ──────────────────────────────────────────────
RSS_FEEDS = [
    # ── 台股 ──
    {
        "source": "鉅亨網",
        "tag": "🇹🇼",
        "kind": "json_api",
        "url": "https://api.cnyes.com/media/api/v1/newslist/category/headline",
        "translate": False,
    },
    {
        "source": "經濟日報",
        "tag": "🇹🇼",
        "kind": "rss",
        "url": "https://money.udn.com/rssfeed/news/1001/5588/12017?ch=money",
        "translate": False,
    },
    {
        "source": "中央社財經",
        "tag": "🇹🇼",
        "kind": "rss",
        "url": "https://feeds.feedburner.com/rsscna/finance",
        "translate": False,
    },
    # ── 美股 / macro ──
    {
        "source": "CNBC",
        "tag": "🇺🇸",
        "kind": "rss",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "translate": True,
    },
    {
        "source": "MarketWatch",
        "tag": "🇺🇸",
        "kind": "rss",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "translate": True,
    },
    {
        "source": "Nikkei Asia",
        "tag": "🇺🇸",
        "kind": "rss",
        "url": "https://asia.nikkei.com/rss/feed/nar",
        "translate": True,
    },
    # ── 加密 ──
    {
        "source": "CoinDesk",
        "tag": "🪙",
        "kind": "rss",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "translate": True,
    },
    {
        "source": "BlockTempo",
        "tag": "🪙",
        "kind": "rss",
        "url": "https://www.blocktempo.com/feed/",
        "translate": False,
    },
]

# ──────────────────────────────────────────────
# 其他常數
# ──────────────────────────────────────────────
# 每個新聞源最多取幾條
NEWS_PER_SOURCE = 2

# 翻譯服務（deep_translator）
TRANSLATOR_SERVICE = "GoogleTranslator"
TRANSLATE_SRC = "en"
TRANSLATE_DST = "zh-TW"

# schema 版本（與 schema/snapshot.schema.json 中的 const 保持一致）
SCHEMA_VERSION = "1.0"
