"""Adidas CI Collector v2 - public sources. FIFA World Cup 2026."""
from __future__ import annotations
import argparse, datetime as dt, json, logging, os, re, sys, time, urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path

import requests
import feedparser  # type: ignore

try:
    from pytrends.request import TrendReq  # type: ignore
    HAS_PYTRENDS = True
except ImportError:
    HAS_PYTRENDS = False

UA = "AdidasCIBot/2.0 (+https://github.com/vinicanola/adidas-warroom)"
HTTP_TIMEOUT = 25
HTTP_HEADERS = {"User-Agent": UA, "Accept": "application/json,text/xml,*/*"}
HISTORY_DAYS = 60

COMPETITORS = [
    {"brand": "Nike",         "category": "Sportswear", "queries": ["Nike", "Nike Football", "Nike Soccer"], "color": "#FA5400"},
    {"brand": "Puma",         "category": "Sportswear", "queries": ["Puma", "Puma Football"], "color": "#E0001A"},
    {"brand": "New Balance",  "category": "Sportswear", "queries": ["New Balance", "New Balance Football"], "color": "#E50020"},
    {"brand": "Under Armour", "category": "Sportswear", "queries": ["Under Armour"], "color": "#E81B23"},
    {"brand": "Mizuno",       "category": "Sportswear", "queries": ["Mizuno"], "color": "#0066CC"},
    # Penalty (Cambuci BR) - keep but rely heavily on EXCLUSION pra evitar 'penalty kick' / 'cobrou penalti'
    {"brand": "Penalty",      "category": "Sportswear", "queries": ["Penalty Esportes", "Penalty futebol"], "color": "#FFC000"},
    {"brand": "Joma",         "category": "Sportswear", "queries": ["Joma"], "color": "#F39200"},
    # DROPADAS por low signal/noise: Asics (running), Umbro (heritage minor), Olympikus (running brand)
]

SELF = {"brand": "Adidas", "category": "Sportswear", "queries": ["Adidas"], "color": "#000000"}
TRENDS_BRANDS = [SELF, *COMPETITORS]

MARKETS = [
    {"code": "BR", "country": "Brasil",    "google_news_locale": "pt-BR",  "google_news_geo": "BR"},
    {"code": "MX", "country": "Mexico",    "google_news_locale": "es-419", "google_news_geo": "MX"},
    {"code": "AR", "country": "Argentina", "google_news_locale": "es-419", "google_news_geo": "AR"},
    {"code": "CO", "country": "Colombia",  "google_news_locale": "es-419", "google_news_geo": "CO"},
]

YOUTUBE_CHANNELS = [
    {"brand": "Adidas",       "handle": "@adidas"},
    {"brand": "Adidas",       "handle": "@adidasfootball"},
    {"brand": "Nike",         "handle": "@Nike"},
    {"brand": "Nike",         "handle": "@nikefootball"},
    {"brand": "Puma",         "handle": "@PUMA"},
    {"brand": "New Balance",  "handle": "@newbalance"},
    {"brand": "Under Armour", "handle": "@UnderArmour"},
    {"brand": "Mizuno",       "handle": "@MizunoOfficial"},
    {"brand": "Penalty",      "handle": "@PenaltyOficial"},
]

COPA_KEYWORDS = [
    # Eventos especificos
    "copa do mundo", "copa mundial", "world cup",
    "mundial 2026", "world cup 2026",
    "fifa world cup", "fifa 2026", "copa fifa",
    # Selecoes (sempre futebol no contexto LATAM)
    "selecao", "seleccion", "selección",
    "selecao brasileira", "seleccion mexicana", "seleccion argentina",
    "seleccion colombiana",
    # Atletas iconicos do Mundial 2026
    "vini jr", "vinicius jr", "neymar", "messi",
    "rodrygo", "lamine yamal", "endrick",
    # Futebol (esporte)
    "futebol", "futbol", "football",
    "torcida", "hincha", "torcedor",
    "fifa",
    # Eliminatorias / qualificacao para a Copa
    "eliminatoria", "qualificat", "qualifying", "play-off",
    # Edicoes/produtos especificamente associados a Copa
    "lata copa", "edicao copa", "edicao mundial",
    "edicion mundial", "edicion copa",
    # Frasings jornalisticos LATAM (Mundial = Copa do Mundo de futebol no contexto)
    "del mundial", "do mundial", "el mundial",
    "no mundial", "en el mundial", "ao mundial",
    "para el mundial", "para o mundial",
    "rumbo al mundial", "rumo ao mundial",
    "el mundialista", "los mundialistas",
]
RED_KEYWORDS = ["lanca", "lanza", "launches", "registra marca", "patrocinio oficial",
                "sponsor", "marca registrada", "edicao comemorativa", "ambush"]
YELLOW_KEYWORDS = ["nova campanha", "new campaign", "investimento", "invierte",
                   "ativacao", "activacion", "promocao", "comemorativa", "patrocina",
                   "anuncia", "estreia"]

# Whitelist de keywords obrigatorias no page_name para o ad ser considerado da marca.
# Filtra lixo do search_terms da Meta (Anyreel, Ns-XXX, Alibaba, etc).
META_BRAND_PAGE_KEYWORDS = {
    "Adidas": [["adidas"]],
    "Nike": [["nike"]],
    "Puma": [["puma"]],
    "New Balance": [["new balance"], ["newbalance"]],
    "Under Armour": [["under armour"], ["underarmour"]],
    "Mizuno": [["mizuno"]],
    "Penalty": [["penalty"]],
    "Joma": [["joma"]],
}

# Page names suspeitos: revendas, marketplaces, scams, contas que abusam do nome da marca.
# Se page_name CONTÉM qualquer dessas, o ad é dropado mesmo se passou no whitelist da marca.
META_PAGE_NAME_BLACKLIST = [
    "lopez brody",     # caso real Adidas: 21 ads de "Lopez Brody Nike" não-oficial
    "jonathan puma",   # pessoa, nao a marca
    "revenda", "atacado", "outlet store", "loja virtual",
    "promocao", "promoção", "desconto",
    "alibaba", "aliexpress", "shein",
    "anyreel", "spotagem",
    # patterns de bot/scam farms
]

# ========== HIERARQUIA OFICIAL FIFA WORLD CUP 2026 ==========
SPONSORSHIP_TIERS = {
    "fifa_partners": [
        {"brand": "Adidas", "category": "Sportswear", "exclusivity": "Apparel/Footwear/Match Ball", "is_self": True},
        {"brand": "Coca-Cola", "category": "Refrigerantes", "exclusivity": "Soft drinks (categoria fechada)"},
        {"brand": "Hyundai-Kia", "category": "Automotivo"},
        {"brand": "Visa", "category": "Pagamentos"},
        {"brand": "Qatar Airways", "category": "Aviacao"},
        {"brand": "Aramco", "category": "Energia"},
    ],
    "world_cup_sponsors": [
        {"brand": "Budweiser", "parent": "Anheuser-Busch InBev", "category": "Cerveja"},
        {"brand": "Hisense", "category": "Eletronicos"},
        {"brand": "McDonald's", "category": "QSR"},
        {"brand": "Mengniu", "category": "Lacteos"},
        {"brand": "Vivo (mobile)", "category": "Telefonia"},
    ],
    "ambush_brands": [
        {"brand": "Nike", "category": "Sportswear", "ambush_target": "Adidas FIFA exclusivity - excecao: Selecao oficial CBF (BR)"},
        {"brand": "Puma", "category": "Sportswear", "ambush_target": "Adidas FIFA exclusivity"},
        {"brand": "New Balance", "category": "Sportswear", "ambush_target": "Adidas FIFA exclusivity"},
        {"brand": "Under Armour", "category": "Sportswear", "ambush_target": "Adidas FIFA exclusivity"},
        {"brand": "Mizuno", "category": "Sportswear", "ambush_target": "Adidas FIFA exclusivity"},
        {"brand": "Penalty", "category": "Sportswear", "ambush_target": "Adidas FIFA exclusivity"},
        {"brand": "Joma", "category": "Sportswear", "ambush_target": "Adidas FIFA exclusivity"},
    ],
}

# Lookup brand -> tier (sponsor_official / ambush_eligible)
def _build_brand_tier_map():
    m = {}
    for s in SPONSORSHIP_TIERS["fifa_partners"]:
        m[s["brand"].lower()] = ("fifa_partner", s)
    for s in SPONSORSHIP_TIERS["world_cup_sponsors"]:
        m[s["brand"].lower()] = ("world_cup_sponsor", s)
    for s in SPONSORSHIP_TIERS["ambush_brands"]:
        m[s["brand"].lower()] = ("ambush_eligible", s)
    return m
_BRAND_TIER_MAP = _build_brand_tier_map()

# ========== PATROCINADORES DAS SELECOES (CBF, AFA, FMF, FCF) ==========
SELECAO_SPONSORS = {
    "BR": [
        {"brand": "Nike", "category": "Sportswear", "tier": "master", "exclusivity": "Apparel oficial CBF - threat principal pro Adidas no BR"},
        {"brand": "Itau", "category": "Banco", "tier": "master"},
        {"brand": "Guarana Antarctica", "category": "Refrigerante", "tier": "master"},
        {"brand": "Powerade", "category": "Isotonico", "tier": "official"},
        {"brand": "Vivo", "category": "Telecom", "tier": "official"},
        {"brand": "Banco do Brasil", "category": "Banco", "tier": "supporter"},
        {"brand": "Brahma", "category": "Cerveja", "tier": "supporter"},
    ],
    "AR": [
        {"brand": "Adidas", "category": "Sportswear", "tier": "master", "is_self": True},
        {"brand": "Quilmes", "category": "Cerveja", "tier": "master"},
        {"brand": "YPF", "category": "Energia", "tier": "official"},
    ],
    "MX": [
        {"brand": "Adidas", "category": "Sportswear", "tier": "master", "is_self": True},
        {"brand": "Coca-Cola", "category": "Refrigerante", "tier": "master", "note": "Coca-Cola FEMSA - dupla licenca FIFA + FMF"},
        {"brand": "Aeromexico", "category": "Aviacao", "tier": "official"},
    ],
    "CO": [
        {"brand": "Adidas", "category": "Sportswear", "tier": "master", "is_self": True},
        {"brand": "Aguila", "category": "Cerveja", "tier": "master"},
        {"brand": "Postobon", "category": "Refrigerante", "tier": "master"},
    ],
}

def _build_selecao_map():
    m = {}
    for market, sponsors in SELECAO_SPONSORS.items():
        for s in sponsors:
            m[(s["brand"].lower(), market)] = s
    return m
_SELECAO_MAP = _build_selecao_map()

# Keywords que ligam um sinal ao Mundial 2026 - igual COPA_KEYWORDS pra consistencia
MUNDIAL_KEYWORDS = COPA_KEYWORDS

# Excluir contextos NAO-relacionados a Copa (F1, MotoGP, NBA, etc)
EXCLUSION_KEYWORDS = [
    # Motorsports (Red Bull, Monster dominantes)
    "f1", " formula 1", "formula1", "formula one",
    "motogp", "moto gp", "motociclismo", "motorsport", "motorsports",
    "nascar", "indycar", "indy car",
    "racing", "grand prix", "gran premio",
    "drift", "kart", "rally",
    # Outros esportes US
    "nfl", "nba", "mlb", "nhl",
    "ufc", "boxing", "mma", "kickbox",
    # Esportes radicais / extremos
    "skate", "skateboard", "skateboarding",
    "surf", "surfing", "surfe", "surfista",
    "snowboard", "freestyle ski", "downhill",
    "bmx", "mtb", "mountain bike", "ciclismo",
    "cliff diving", "wakeboard", "kitesurf",
    "parkour", "freerun",
    # Esports / gaming (FGC e cia da Red Bull)
    "esports", "e-sports", "gaming",
    "fgc", "tekken", "street fighter", "capcom",
    "trackmania", "soapbox", "wings for life",
    "videogame", "video game", "videogame",
    "fortnite", "league of legends",
    # Cultura / musica
    "festival", "concerto", "concert", "show musical",
    "rock in rio", "lollapalooza",
    # Esportes nao-soccer (running/maraton) - importante para dropar Mizuno/Olympikus running content
    "maratona", "marathon", "corrida de rua", "ultramaraton",
    # Falsos positivos especificos do contexto Adidas (queries colidem com termos comuns)
    "penalty kick", "cobrou penalti", "cobrou pênalti", "marcou penalti", "marcou pênalti",
    "penalty statistics", "perdeu penalti", "perdeu pênalti", "missed penalty",
    "penalty shocker", "penalty shootout", "penalty shoot-out", "penalty shoot out",
    "disputa de penaltis", "disputa de pênaltis", "penalty corner",
    "penalty miss", "saves penalty", "save penalty", "saved a penalty",
    "puma rodriguez", "puma rodríguez",  # jogador de futebol do Vasco
    # Noticias de marca registrada / propriedade intelectual - puro noise
    "registro de marca", "registra marca", "propriedade intelectual",
    "lei da propriedade", "infracao de marca", "infração de marca",
    "perde direito", "alto renome", "marca de alto renome",
]


def classify_sponsorship(brand, title, market="GLOBAL"):
    """Retorna 'fifa_official', 'selecao_oficial', 'ambush', ou 'neutral'.
    A classificacao e por mercado. Exemplo: Nike e selecao_oficial em BR (CBF),
    mas ambush em MX/AR/CO (onde Adidas e o oficial das selecoes)."""
    brand_l = (brand or "").lower()
    title_l = (title or "").lower()
    if not brand_l:
        return "neutral"
    if any(k in title_l for k in EXCLUSION_KEYWORDS):
        return "neutral"
    has_mundial = any(k in title_l for k in MUNDIAL_KEYWORDS)
    if not has_mundial:
        return "neutral"

    # 1. FIFA tier first (global, overrides selecao)
    tier_info = _BRAND_TIER_MAP.get(brand_l)
    if tier_info and tier_info[0] in ("fifa_partner", "world_cup_sponsor"):
        return "fifa_official"

    # 2. Selecao sponsor for this market
    if (brand_l, market) in _SELECAO_MAP:
        return "selecao_oficial"

    # 3. Ambush eligible
    if tier_info and tier_info[0] == "ambush_eligible":
        return "ambush"

    return "neutral"


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("collector")


@dataclass
class Signal:
    level: str
    title: str
    market: str
    source: str
    url: str
    timestamp: str
    brand: str
    category: str
    raw_meta: dict = field(default_factory=dict)


def http_get(url, params=None, headers=None, timeout=HTTP_TIMEOUT):
    try:
        r = requests.get(url, params=params, headers={**HTTP_HEADERS, **(headers or {})},
                         timeout=timeout)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        body = ""
        if getattr(e, "response", None) is not None:
            body = (e.response.text or "")[:300].replace("\n", " ")
        log.warning("HTTP fail %s: %s | body: %s", url, str(e)[:120], body)
        return None


def classify(title):
    t = title.lower()
    if any(k in t for k in RED_KEYWORDS):
        return "red"
    if any(k in t for k in YELLOW_KEYWORDS):
        return "yellow"
    return "green"


def is_relevant(title):
    """Filtro principal: titulo precisa ser sobre futebol/Mundial 2026 E nao
    ser de esporte excluso (F1, skate, gaming, etc). Aplicado em todos os
    coletores que trazem feed de noticias/videos."""
    if not title:
        return False
    t = title.lower()
    # Se tem palavra de exclusao, descarta imediato (Red Bull F1, Monster skate, etc)
    if any(k in t for k in EXCLUSION_KEYWORDS):
        return False
    # Precisa ter pelo menos uma palavra de futebol/Mundial
    return any(k in t for k in COPA_KEYWORDS)


# Alias para compatibilidade com collect_youtube_uploads
is_football_relevant = is_relevant


def humanize_time(ts_iso):
    try:
        ts = dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        delta = dt.datetime.now(dt.timezone.utc) - ts
        if delta.days > 0:
            return f"ha {delta.days}d"
        h = delta.seconds // 3600
        if h > 0:
            return f"ha {h}h"
        return f"ha {max(1, delta.seconds // 60)} min"
    except Exception:
        return "-"


def days_ago(ts_iso):
    if not ts_iso:
        return 999
    ts = None
    # Try ISO 8601 (e.g. "2026-05-03T22:38:34+00:00" or "...Z")
    try:
        ts = dt.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
    except Exception:
        pass
    # Try RFC 822 (RSS feeds: "Wed, 30 Apr 2026 14:32:00 GMT")
    if ts is None:
        try:
            from email.utils import parsedate_to_datetime
            ts = parsedate_to_datetime(ts_iso)
        except Exception:
            pass
    # Try GDELT compact format ("20260430T143200Z")
    if ts is None:
        try:
            ts = dt.datetime.strptime(ts_iso[:15], "%Y%m%dT%H%M%S")
            ts = ts.replace(tzinfo=dt.timezone.utc)
        except Exception:
            pass
    if ts is None:
        return 999
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - ts).days


# -------------------- Coletores --------------------

def collect_google_news():
    signals = []
    for market in MARKETS:
        for comp in COMPETITORS:
            for q in comp["queries"]:
                query = f'"{q}" (copa OR mundial OR "world cup" OR "edicao limitada" OR "edicion especial")'
                url = ("https://news.google.com/rss/search"
                       f"?q={urllib.parse.quote(query)}"
                       f"&hl={market['google_news_locale']}"
                       f"&gl={market['google_news_geo']}"
                       f"&ceid={market['google_news_geo']}:{market['google_news_locale'].split('-')[0]}")
                feed = feedparser.parse(url)
                for entry in feed.entries[:8]:
                    title = entry.get("title", "")
                    title_lower = title.lower()
                    # Hard block: exclusao keyword ALWAYS pula, mesmo se a marca esta no titulo
                    # (resolve "Di Maria penalty shocker" capturando query "Penalty")
                    if any(kw in title_lower for kw in EXCLUSION_KEYWORDS):
                        continue
                    if not is_relevant(title) and q.lower() not in title_lower:
                        continue
                    signals.append(Signal(
                        level=classify(title),
                        title=title,
                        market=market["code"],
                        source=f"Google News {market['code']}",
                        url=entry.get("link", ""),
                        timestamp=entry.get("published", dt.datetime.utcnow().isoformat() + "Z"),
                        brand=comp["brand"],
                        category=comp["category"],
                    ))
                time.sleep(0.25)
    return signals


def collect_inpi_proxy():
    signals = []
    for comp in COMPETITORS:
        for q in comp["queries"][:1]:
            query = f'"{q}" (registro OR marca) (INPI OR "propriedade industrial")'
            url = ("https://news.google.com/rss/search"
                   f"?q={urllib.parse.quote(query)}&hl=pt-BR&gl=BR&ceid=BR:pt")
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                lt = title.lower()
                if "marca" not in lt and "registro" not in lt and "inpi" not in lt:
                    continue
                signals.append(Signal(
                    level="yellow",
                    title=f"[Registro/marca] {title}",
                    market="BR",
                    source="INPI proxy",
                    url=entry.get("link", ""),
                    timestamp=entry.get("published", dt.datetime.utcnow().isoformat() + "Z"),
                    brand=comp["brand"],
                    category=comp["category"],
                ))
                time.sleep(0.2)
    return signals


def collect_gdelt():
    signals = []
    for comp in COMPETITORS[:8]:
        q = comp["queries"][0]
        params = {
            "query": f'"{q}" sourcelang:eng OR sourcelang:por OR sourcelang:spa',
            "mode": "ArtList", "maxrecords": 25, "format": "json",
            "sort": "DateDesc", "timespan": "60d",
        }
        r = http_get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=15)
        if not r:
            continue
        try:
            articles = r.json().get("articles", [])
        except json.JSONDecodeError:
            continue
        for a in articles[:10]:
            title = a.get("title", "")
            if not title or not is_relevant(title):
                continue
            signals.append(Signal(
                level=classify(title),
                title=title,
                market=(a.get("sourcecountry") or "GLOBAL")[:2].upper(),
                source=f"GDELT {a.get('domain', '')}",
                url=a.get("url", ""),
                timestamp=a.get("seendate", "") or dt.datetime.utcnow().isoformat() + "Z",
                brand=comp["brand"],
                category=comp["category"],
            ))
        time.sleep(0.5)
    return signals


def collect_mercadolibre():
    """Coleta lancamentos oficiais Mundial 2026: camisas/jerseys de selecoes,
    chuteiras signature, bolas oficiais. Substitui o conceito de 'latas comemorativas'
    do template original pelo equivalente em Sportswear."""
    latas = []
    sites = [("MLB", "BR"), ("MLM", "MX"), ("MLA", "AR"), ("MCO", "CO")]
    queries = [
        # Camisas / jerseys de selecoes
        "camisa selecao 2026", "jersey mundial 2026", "kit oficial selecao",
        "camisa brasil 2026", "camisa mexico 2026", "camisa argentina 2026",
        # Chuteiras signature / Mundial-themed
        "chuteira predator", "chuteira mercurial", "chuteira mundial 2026",
        "chuteira vini jr", "chuteira messi", "chuteira mbappe",
        # Bolas oficiais
        "bola oficial fifa 2026", "match ball mundial", "bola copa do mundo 2026",
    ]
    for site_id, mkt in sites:
        for q in queries:
            url = f"https://api.mercadolibre.com/sites/{site_id}/search"
            r = http_get(url, params={"q": q, "limit": 8})
            if not r:
                continue
            try:
                items = r.json().get("results", [])
            except json.JSONDecodeError:
                continue
            for it in items:
                title = it.get("title", "")
                # Inclui SELF (Adidas) na busca - lancamentos da propria marca tambem importam
                matched = next((c for c in [SELF, *COMPETITORS]
                                if any(qq.lower() in title.lower() for qq in c["queries"])), None)
                if not matched:
                    continue
                latas.append({
                    "brand": matched["brand"],
                    "sku": it.get("id", ""),
                    "label": title[:55],
                    "color": matched["color"],
                    "market": mkt,
                    "tag": "Lancamento detectado em e-commerce",
                    "url": it.get("permalink", ""),
                    "price": it.get("price"),
                })
            time.sleep(0.3)
    return latas


def collect_google_trends():
    if not HAS_PYTRENDS:
        log.warning("pytrends nao instalado")
        return {}
    out = {"global": {"labels": [], "series": {}}, "by_market": {}}
    groups = [
        ["Adidas", "Nike", "Puma", "New Balance", "Under Armour"],
        ["Adidas", "Mizuno", "Penalty", "Joma"],
    ]
    geos = {"global": "", "BR": "BR", "MX": "MX", "AR": "AR", "CO": "CO"}
    for geo_label, geo in geos.items():
        market_data = {"labels": [], "series": {}}
        try:
            pytrends = TrendReq(hl="pt-BR", tz=180, timeout=(10, 25),
                                requests_args={"headers": {"User-Agent": UA}})
            for group in groups:
                pytrends.build_payload(group, cat=0, timeframe="today 3-m", geo=geo, gprop="")
                df = pytrends.interest_over_time()
                if df is None or df.empty:
                    continue
                if "isPartial" in df.columns:
                    df = df.drop(columns=["isPartial"])
                df = df.tail(60)
                if not market_data["labels"]:
                    market_data["labels"] = [d.strftime("%Y-%m-%d") for d in df.index]
                for col in df.columns:
                    if col not in market_data["series"]:
                        market_data["series"][col] = df[col].astype(int).tolist()
                time.sleep(2)
        except Exception as e:
            log.warning("Google Trends %s falhou: %s", geo_label, str(e)[:120])
            continue
        if geo_label == "global":
            out["global"] = market_data
        else:
            out["by_market"][geo_label] = market_data
    return out


def collect_wikipedia_pageviews():
    out = {}
    end = dt.date.today() - dt.timedelta(days=1)
    start = end - dt.timedelta(days=HISTORY_DAYS - 1)
    base = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
    articles = [
        ("Adidas", "pt.wikipedia", "Adidas"),
        ("Nike", "pt.wikipedia", "Nike,_Inc."),
        ("Puma", "pt.wikipedia", "Puma_(empresa)"),
        ("New Balance", "pt.wikipedia", "New_Balance"),
        ("Under Armour", "pt.wikipedia", "Under_Armour"),
        ("Mizuno", "pt.wikipedia", "Mizuno"),
        ("Penalty", "pt.wikipedia", "Penalty_(empresa)"),
        ("Joma", "pt.wikipedia", "Joma_Sport"),
    ]
    for brand, project, article in articles:
        url = (f"{base}/{project}/all-access/all-agents/{article}/daily/"
               f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}")
        r = http_get(url, headers={"Accept": "application/json"})
        if not r:
            continue
        try:
            items = r.json().get("items", [])
        except json.JSONDecodeError:
            continue
        out[brand] = [{"date": x["timestamp"][:8], "views": x["views"]} for x in items]
        time.sleep(0.4)
    return out


def _resolve_youtube_channel_id(handle):
    url = f"https://www.youtube.com/{handle}"
    r = http_get(url, headers={"Accept-Language": "en"}, timeout=10)
    if not r:
        return None
    m = re.search(r'"channelId":"(UC[\w-]{20,30})"', r.text)
    if m:
        return m.group(1)
    m = re.search(r'"externalId":"(UC[\w-]{20,30})"', r.text)
    return m.group(1) if m else None


def collect_youtube_uploads():
    out = []
    for ch in YOUTUBE_CHANNELS:
        cid = _resolve_youtube_channel_id(ch["handle"])
        if not cid:
            log.warning("YouTube: nao resolveu %s", ch["handle"])
            continue
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        feed = feedparser.parse(feed_url)
        # Filtra apenas videos relacionados a futebol/Mundial (descarta skate, gaming, F1, etc)
        for entry in feed.entries[:25]:  # busca mais videos pra compensar filtro
            title = entry.get("title", "")
            if not is_football_relevant(title):
                continue
            video_id = entry.get("yt_videoid") or (
                entry.get("link", "").split("v=")[-1] if "v=" in entry.get("link", "") else "")
            out.append({
                "brand": ch["brand"],
                "channel": entry.get("author", ch["handle"]),
                "title": title[:90],
                "published_at": entry.get("published", ""),
                "video_id": video_id,
                "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg" if video_id else "",
                "url": entry.get("link", ""),
            })
            if len([v for v in out if v["brand"] == ch["brand"]]) >= 5:
                break  # max 5 por canal
        time.sleep(0.5)
    out.sort(key=lambda x: x["published_at"], reverse=True)
    return out[:20]


def _is_legit_brand_page(brand, page_name):
    """Retorna True se page_name parece ser de uma Page oficial da marca.
    Filtra anuncios de marketplaces, scams e contas que so usam o nome da marca como keyword."""
    pn = (page_name or "").lower()
    if not pn:
        return False
    # Blacklist explicita de patterns suspeitos (revendas, marketplaces, scams)
    for blocked in META_PAGE_NAME_BLACKLIST:
        if blocked in pn:
            return False
    groups = META_BRAND_PAGE_KEYWORDS.get(brand, [[brand.lower()]])
    for grp in groups:
        if all(kw in pn for kw in grp):
            return True
    return False


def _ad_copa_score(text):
    """Pontua o quanto um anuncio é relevante pra Mundial 2026.
    Reusa COPA_KEYWORDS. Bonus extra pra mencao explicita."""
    if not text:
        return 0
    t = text.lower()
    score = 0
    for kw in COPA_KEYWORDS:
        if kw in t:
            score += 2
    if "2026" in t and any(k in t for k in ["mundial","copa","world cup","fifa"]):
        score += 5
    return score


def collect_meta_ad_library():
    token = os.environ.get("META_AD_LIBRARY_TOKEN", "").strip()
    out = []
    if not token:
        log.info("META_AD_LIBRARY_TOKEN nao definido - pulando Meta Ad Library")
        return out
    # v21.0 - v18 deprecada em ago/2026 mas ainda funciona; v21 da margem
    base = "https://graph.facebook.com/v21.0/ads_archive"
    fields = "id,page_name,ad_creative_bodies,ad_creative_link_titles,ad_creative_link_descriptions,ad_delivery_start_time,publisher_platforms"
    # Inclui SELF na busca - util para benchmarking de share-of-voice e sanity check da integracao
    brands_to_search = [SELF, *COMPETITORS]
    for country in ["BR", "MX", "AR", "CO"]:
        for comp in brands_to_search:
            params = {
                "search_terms": comp["queries"][0],
                "ad_active_status": "ACTIVE",
                "ad_reached_countries": country,
                "fields": fields,
                # Over-fetch: filtro de page_name vai dropar a maioria do lixo
                "limit": 25,
                "access_token": token,
            }
            r = http_get(base, params=params, timeout=20)
            if not r:
                continue
            try:
                data = r.json().get("data", [])
            except json.JSONDecodeError:
                continue
            for ad in data:
                page_name = ad.get("page_name", "")
                # Filtro: drop ads de Pages que nao sao da marca
                if not _is_legit_brand_page(comp["brand"], page_name):
                    continue
                bodies = ad.get("ad_creative_bodies") or []
                titles = ad.get("ad_creative_link_titles") or []
                descs = ad.get("ad_creative_link_descriptions") or []
                full_text = " ".join(bodies + titles + descs)
                score = _ad_copa_score(full_text)
                ad_id = ad.get("id", "")
                out.append({
                    "brand": comp["brand"],
                    "page_name": page_name,
                    "country": country,
                    "platform": ",".join(ad.get("publisher_platforms") or []),
                    "started_at": (ad.get("ad_delivery_start_time") or "")[:10],
                    "body_snippet": (bodies[0] if bodies else "")[:200],
                    "title": (titles[0] if titles else "")[:120],
                    # URL publica do Ad Library — SEM TOKEN. Usuario clica e ve o ad no browser dele.
                    "ad_url": "https://www.facebook.com/ads/library/?id={}".format(ad_id) if ad_id else "",
                    "ad_id": ad_id,
                    "copa_score": score,
                })
            time.sleep(0.3)
    # Sort: COPA-relevantes primeiro, depois mais recentes
    out.sort(key=lambda x: (x.get("copa_score", 0), x.get("started_at", "")), reverse=True)
    return out


def collect_trending_topics():
    """Substitui collect_tiktok_tags - usa Google Trends 'rising queries' como
    fonte de topicos em alta (TikTok Creative Center bloqueia IPs do GitHub Actions).
    Retorna formato compativel com tiktok_tags pro dashboard nao mudar."""
    if not HAS_PYTRENDS:
        log.warning("pytrends nao instalado - skip trending_topics")
        return []
    out = []
    seeds_by_market = {
        "BR": ["Mundial 2026", "Copa do Mundo 2026", "Selecao Brasileira"],
        "MX": ["Mundial 2026", "Seleccion mexicana"],
        "AR": ["Mundial 2026", "Seleccion argentina"],
        "CO": ["Mundial 2026", "Seleccion colombiana"],
    }
    seen = set()  # dedup por (tag, country)
    for country, seeds in seeds_by_market.items():
        for seed in seeds:
            try:
                pytrends = TrendReq(hl="pt-BR", tz=180, timeout=(10, 20),
                                    requests_args={"headers": {"User-Agent": UA}})
                pytrends.build_payload([seed], timeframe="today 1-m", geo=country, gprop="")
                related = pytrends.related_queries() or {}
                seed_data = related.get(seed, {}) or {}
                rising = seed_data.get("rising")
                if rising is None or (hasattr(rising, "empty") and rising.empty):
                    continue
                for _, row in rising.head(5).iterrows():
                    query = row.get("query", "")
                    value = row.get("value", 0)
                    if not query:
                        continue
                    if isinstance(value, str) and "breakout" in value.lower():
                        growth = 999
                    else:
                        try:
                            growth = int(value)
                        except (ValueError, TypeError):
                            growth = 0
                    tag_clean = re.sub(r"[^\w]+", "", query.lower())[:30]
                    if not tag_clean:
                        continue
                    key = (tag_clean, country)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({
                        "tag": "#" + tag_clean,
                        "country": country,
                        "posts": 0,
                        "rank": len(out) + 1,
                        "growth_pct": growth,
                        "raw_query": query,
                        "seed": seed,
                    })
                time.sleep(2)
            except Exception as e:
                log.warning("Trending topics %s/%s falhou: %s", country, seed, str(e)[:120])
                continue
    out.sort(key=lambda t: -t.get("growth_pct", 0))
    # re-rank apos sort
    for i, t in enumerate(out):
        t["rank"] = i + 1
    return out[:20]


def collect_tiktok_tags():
    out = []
    for code, region in [("BR", "BR"), ("MX", "MX"), ("AR", "AR"), ("CO", "CO")]:
        url = "https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
        params = {"page": 1, "limit": 20, "period": 30, "country_code": region, "sort_by": "popular"}
        r = http_get(url, params=params, headers={
            "Accept": "application/json",
            "Referer": "https://ads.tiktok.com/business/creativecenter/",
            "Lang": "en",
        }, timeout=15)
        if not r:
            continue
        try:
            data = r.json().get("data", {})
            tags = data.get("list", []) or []
        except (json.JSONDecodeError, AttributeError):
            continue
        for t in tags[:10]:
            tag_name = t.get("hashtag_name", "")
            tag_lower = tag_name.lower()
            keep = any(kw in tag_lower for kw in
                       ["copa", "mundial", "fifa", "futbol", "futebol", "selec",
                        "adidas", "nike", "puma", "newbalance",
                        "vinijr", "vinicius", "neymar", "messi", "mbappe", "lamineyamal"])
            if keep or t.get("rank", 999) <= 3:
                out.append({
                    "tag": "#" + tag_name,
                    "country": code,
                    "posts": t.get("publish_cnt", 0),
                    "rank": t.get("rank", 0),
                    "growth_pct": int(t.get("trend", 0)),
                })
        time.sleep(0.5)
    return out


# -------------------- Agregacao --------------------

# Termos que indicam lancamento de produto (lata/garrafa/colecao/edicao especial)
PRODUCT_KEYWORDS = [
    "lata", "garrafa", "botella", "bottle",
    "pack", "kit",
    "colecao", "coleção", "coleccion", "colección", "coleccionable",
    "edicao", "edição", "edicion", "edición",
]


def infer_latas_from_signals(signal_objs, existing_latas):
    """Cria 'latas provisorias' a partir de sinais red/yellow que mencionam
    container/edicao/colecao. Dedup por brand+market e nao duplica com latas
    de e-commerce ja detectadas."""
    competitors_by_brand = {c["brand"]: c for c in COMPETITORS}
    ecom_keys = {f"{l.get('brand', '')}_{l.get('market', '')}" for l in existing_latas}
    seen_keys = set()
    inferred = []
    for s in signal_objs:
        if s.level not in ("red", "yellow"):
            continue
        title_lower = s.title.lower()
        if not any(kw in title_lower for kw in PRODUCT_KEYWORDS):
            continue
        comp = competitors_by_brand.get(s.brand)
        if not comp:
            continue
        key = f"{s.brand}_{s.market}"
        if key in seen_keys or key in ecom_keys:
            continue
        seen_keys.add(key)
        inferred.append({
            "brand": s.brand,
            "sku": f"signal-{abs(hash(s.title + s.brand)) % 100000000}",
            "label": s.title[:55],
            "color": comp["color"],
            "market": s.market,
            "tag": "Sinal de imprensa - aguardando estoque",
            "url": s.url,
            "price": None,
        })
    return inferred


def compute_competitor_stats(signals, latas, active_ads, yt):
    rows = []
    for c in COMPETITORS:
        my_signals = [s for s in signals if s.brand == c["brand"]]
        my_latas = [l for l in latas if l["brand"] == c["brand"]]
        my_ads = [a for a in active_ads if a.get("brand") == c["brand"]]
        my_yt = [v for v in yt if v.get("brand") == c["brand"]]
        red_yellow = [s for s in my_signals if s.level in ("red", "yellow")]
        top = red_yellow[0] if red_yellow else (my_signals[0] if my_signals else None)
        rows.append({
            "brand": c["brand"],
            "category": c["category"],
            "color": c["color"],
            "signals_60d": len(my_signals),
            "latas_detected": len(my_latas),
            "ads_active": len(my_ads),
            "youtube_uploads_30d": len([v for v in my_yt if days_ago(v.get("published_at", "")) <= 30]),
            "top_movement": top.title[:90] if top else "Sem movimento relevante",
            "top_source": top.source if top else "",
        })
    return rows


def compute_market_scores(signals):
    out = []
    flags = {"BR": "\U0001F1E7\U0001F1F7", "MX": "\U0001F1F2\U0001F1FD",
             "AR": "\U0001F1E6\U0001F1F7", "CO": "\U0001F1E8\U0001F1F4"}
    for m in MARKETS:
        my = [s for s in signals if s.market == m["code"]]
        weight = sum(5 if s.level == "red" else 2 if s.level == "yellow" else 1 for s in my)
        out.append({
            "country": m["country"], "code": m["code"], "flag": flags.get(m["code"], ""),
            "score": min(100, weight), "signals": len(my),
            "color": {"BR": "#F40000", "MX": "#006847", "AR": "#75AADB", "CO": "#FFCD00"}[m["code"]],
        })
    return out


def compute_kpis(signals, active_ads, latas, trends):
    ads_by_brand = {}
    for a in active_ads:
        b = a.get("brand", "")
        ads_by_brand[b] = ads_by_brand.get(b, 0) + 1
    if ads_by_brand:
        top_ads_brand = max(ads_by_brand, key=ads_by_brand.get)
        top_ads_count = ads_by_brand[top_ads_brand]
    else:
        top_ads_brand = "-"
        top_ads_count = 0

    leader_brand, leader_pct, leader_delta = "-", 0, 0
    series = (trends or {}).get("global", {}).get("series", {})
    if series:
        latest_avg = {b: sum(v[-7:]) / max(len(v[-7:]), 1) for b, v in series.items() if v}
        if latest_avg:
            leader_brand = max(latest_avg, key=latest_avg.get)
            leader_pct = round(latest_avg[leader_brand], 1)
            prev = series.get(leader_brand, [])
            if len(prev) >= 14:
                prev_avg = sum(prev[-14:-7]) / 7
                leader_delta = round(leader_pct - prev_avg, 1)

    signals_60d = len(signals)
    recent_30 = sum(1 for s in signals if days_ago(s.timestamp) <= 30)
    older_30 = sum(1 for s in signals if 30 < days_ago(s.timestamp) <= 60)
    delta_pct = round(100 * (recent_30 - older_30) / max(older_30, 1), 0) if older_30 else 0

    return {
        "ads_active_total": sum(ads_by_brand.values()),
        "ads_active_top_brand": top_ads_brand,
        "ads_active_top_count": top_ads_count,
        "search_leader_brand": leader_brand,
        "search_leader_pct": leader_pct,
        "search_leader_delta_pp": leader_delta,
        "signals_60d": signals_60d,
        "signals_delta_pct": int(delta_pct),
        "latas_total": len(latas),
        "latas_unvalidated": sum(1 for l in latas if l.get("tag", "").startswith("Sinal")),
    }


def load_existing(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def merge_signals(existing, new_signals):
    by_key = {}
    # Filtra mock data (URLs example.com) ao ler existente
    # E re-aplica EXCLUSION_KEYWORDS pra limpar signals coletados quando o filtro era mais frouxo
    for s in existing:
        url = s.get("url", "")
        if "example.com" in url or "example.org" in url:
            continue  # descarta mock seed
        title_l = (s.get("title", "") or "").lower()
        if any(kw in title_l for kw in EXCLUSION_KEYWORDS):
            continue  # signal antigo agora considerado off-topic - drop
        key = re.sub(r"\W+", "", (s.get("title", "")).lower())[:80] + s.get("brand", "")
        by_key[key] = s
    for s in new_signals:
        key = re.sub(r"\W+", "", s.title.lower())[:80] + s.brand
        if key not in by_key:
            d = asdict(s)
            d["time_human"] = humanize_time(s.timestamp)
            by_key[key] = d
    # Filtra signals de marcas que nao estao mais sendo monitoradas (ex: Red Bull dropped)
    active_brands = {SELF["brand"], *[c["brand"] for c in COMPETITORS]}
    out = [s for s in by_key.values()
           if days_ago(s.get("timestamp", "")) <= HISTORY_DAYS
           and s.get("brand", "") in active_brands]
    level_order = {"red": 0, "yellow": 1, "green": 2}
    out.sort(key=lambda s: (level_order.get(s.get("level", "green"), 3),
                            -days_ago(s.get("timestamp", ""))))
    return out


def main(dry_run=False):
    log.info("=== CI Collector v2 ===")
    sources_health = {}
    out_path = Path(__file__).parent / "data" / "latest.json"
    existing = load_existing(out_path)

    all_signals_new = []
    latas, yt, active_ads, tiktok = [], [], [], []
    trends, wiki = {}, {}

    for name, fn in [("google_news", collect_google_news),
                     ("gdelt", collect_gdelt),
                     ("inpi_proxy", collect_inpi_proxy)]:
        t0 = time.time()
        try:
            sigs = fn()
            all_signals_new.extend(sigs)
            sources_health[name] = {"status": "ok", "count": len(sigs),
                                    "elapsed_s": round(time.time() - t0, 1)}
            log.info("%s: %d sinais", name, len(sigs))
        except Exception as e:
            sources_health[name] = {"status": "error", "error": str(e)[:160]}
            log.exception("Falha no coletor %s", name)

    for name, fn in [("mercadolibre", collect_mercadolibre),
                     ("youtube_rss", collect_youtube_uploads),
                     ("meta_ad_library", collect_meta_ad_library),
                     ("trending_topics", collect_trending_topics),
                     ("google_trends", collect_google_trends),
                     ("wikipedia", collect_wikipedia_pageviews)]:
        t0 = time.time()
        try:
            result = fn()
            if name == "mercadolibre": latas = result
            elif name == "youtube_rss": yt = result
            elif name == "meta_ad_library": active_ads = result
            elif name == "trending_topics": tiktok = result
            elif name == "google_trends": trends = result
            elif name == "wikipedia": wiki = result
            count = len(result) if isinstance(result, (list, dict)) else 0
            sources_health[name] = {"status": "ok", "count": count,
                                    "elapsed_s": round(time.time() - t0, 1)}
            log.info("%s: %d itens", name, count)
        except Exception as e:
            sources_health[name] = {"status": "error", "error": str(e)[:160]}
            log.exception("Falha no coletor %s", name)

    # Fallback: preserve previous run's data when new collection returned empty
    def _has_trends(t):
        return bool(t and (t.get("global", {}) or {}).get("series"))

    # Brands ativos em trends (vide groups em collect_google_trends + Coca-Cola)
    _trends_brands = {"Adidas", "Nike", "Puma", "New Balance", "Under Armour",
                       "Mizuno", "Penalty", "Joma"}

    def _prune_trends(t):
        if not t: return t
        for key in ("global",):
            if key in t and isinstance(t[key], dict) and "series" in t[key]:
                t[key]["series"] = {b: v for b, v in t[key]["series"].items() if b in _trends_brands}
        if "by_market" in t and isinstance(t["by_market"], dict):
            for mkt in list(t["by_market"]):
                if "series" in t["by_market"][mkt]:
                    t["by_market"][mkt]["series"] = {b: v for b, v in t["by_market"][mkt]["series"].items() if b in _trends_brands}
        return t

    trends = _prune_trends(trends)

    if not _has_trends(trends):
        prev = (existing or {}).get("search_interest")
        if _has_trends(prev):
            log.info("google_trends vazio - reaproveitando dados do run anterior")
            trends = _prune_trends(prev)
            sources_health.setdefault("google_trends", {})["fallback"] = "kept_previous"

    # Active brands para limpar fallbacks de marcas que nao estao mais sendo monitoradas
    _active_brands = {SELF["brand"], *[c["brand"] for c in COMPETITORS]}

    if not wiki:
        prev = (existing or {}).get("wikipedia_pageviews")
        if prev:
            prev = {b: v for b, v in prev.items() if b in _active_brands}
        if prev:
            log.info("wikipedia vazio - reaproveitando dados do run anterior")
            wiki = prev
            sources_health.setdefault("wikipedia", {})["fallback"] = "kept_previous"

    if not yt:
        prev = (existing or {}).get("youtube_uploads")
        if prev:
            prev = [v for v in prev if v.get("brand", "") in _active_brands]
        if prev:
            log.info("youtube_uploads vazio - reaproveitando dados do run anterior")
            yt = prev
            sources_health.setdefault("youtube_rss", {})["fallback"] = "kept_previous"

    if not active_ads:
        prev = (existing or {}).get("active_ads")
        if prev:
            # Re-aplica filtros atuais no fallback (page_name blacklist + brand whitelist)
            # pra evitar que ads bloqueados por filtros novos sobrevivam via kept_previous
            prev = [a for a in prev
                    if a.get("brand", "") in _active_brands
                    and _is_legit_brand_page(a.get("brand", ""), a.get("page_name", ""))]
        if prev:
            log.info("active_ads vazio - reaproveitando %d ads do run anterior (apos re-filter)", len(prev))
            active_ads = prev
            sources_health.setdefault("meta_ad_library", {})["fallback"] = "kept_previous"

    existing_signals = existing.get("signals", []) if existing else []
    merged_signals = merge_signals(existing_signals, all_signals_new)
    log.info("Total sinais merged: %d", len(merged_signals))

    # Classifica sponsorship_status em cada sinal merged (por market)
    for s in merged_signals:
        s["sponsorship_status"] = classify_sponsorship(s.get("brand", ""), s.get("title", ""), s.get("market", "GLOBAL"))

    signal_objs = []
    for s in merged_signals:
        try:
            signal_objs.append(Signal(
                level=s.get("level", "green"),
                title=s.get("title", ""),
                market=s.get("market", "GLOBAL"),
                source=s.get("source", ""),
                url=s.get("url", ""),
                timestamp=s.get("timestamp", ""),
                brand=s.get("brand", ""),
                category=s.get("category", ""),
            ))
        except Exception:
            continue

    # Cross-link: gera latas provisorias a partir de sinais sobre lancamento
    inferred_latas = infer_latas_from_signals(signal_objs, latas)
    if inferred_latas:
        log.info("Latas inferidas de sinais: %d", len(inferred_latas))
        latas = latas + inferred_latas

    kpis = compute_kpis(signal_objs, active_ads, latas, trends)
    # KPIs por status de patrocinio
    fifa_signals = [s for s in merged_signals if s.get("sponsorship_status") == "fifa_official"]
    selecao_signals = [s for s in merged_signals if s.get("sponsorship_status") == "selecao_oficial"]
    ambush_signals = [s for s in merged_signals if s.get("sponsorship_status") == "ambush"]
    ambush_by_brand = {}
    for s in ambush_signals:
        b = s.get("brand", "")
        ambush_by_brand[b] = ambush_by_brand.get(b, 0) + 1
    top_ambush_brand = max(ambush_by_brand, key=ambush_by_brand.get) if ambush_by_brand else "-"
    top_ambush_count = ambush_by_brand[top_ambush_brand] if ambush_by_brand else 0
    kpis["ambush_attempts_total"] = len(ambush_signals)
    kpis["ambush_top_brand"] = top_ambush_brand
    kpis["ambush_top_count"] = top_ambush_count
    kpis["fifa_signals_total"] = len(fifa_signals)
    kpis["selecao_signals_total"] = len(selecao_signals)
    # Backwards-compat alias
    kpis["official_signals_total"] = len(fifa_signals)

    markets = compute_market_scores(signal_objs)
    competitor_stats = compute_competitor_stats(signal_objs, latas, active_ads, yt)

    output = {
        "schema_version": 2,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "history_days": HISTORY_DAYS,
        "sources_health": sources_health,
        "competitors": [{"brand": c["brand"], "category": c["category"], "color": c["color"]}
                        for c in COMPETITORS],
        "markets": markets,
        "kpis": kpis,
        "signals": merged_signals[:200],
        "search_interest": trends,
        "wikipedia_pageviews": wiki,
        "active_ads": active_ads[:80],
        "youtube_uploads": yt,
        "tiktok_tags": tiktok,
        "latas": latas[:30],
        "competitor_stats": competitor_stats,
        "sponsorship_tiers": SPONSORSHIP_TIERS,
        "selecao_sponsors": SELECAO_SPONSORS,
        "ambush_by_brand": ambush_by_brand,
    }

    payload = json.dumps(output, indent=2, ensure_ascii=False)
    if dry_run:
        print(payload[:4000])
        return 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    log.info("Escrito: %s (%d bytes)", out_path, len(payload))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
