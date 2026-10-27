"""Haber kaynakları: Google News RSS (anahtar kelime keşfi) + site RSS'leri."""
from __future__ import annotations

import hashlib
import re
import time
import urllib.parse

import feedparser

UA = "haber-radar/0.1"
# Google News, bot gibi görünen UA ve art arda gelen sorgularda sessizce boş yanıt verebiliyor
GN_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def make_item(title: str, url: str, category: str, source: str,
              published: str | None = None, site: str | None = None) -> dict | None:
    title = re.sub(r"<[^>]+>", "", title or "").strip()
    if not title or not url:
        return None
    return {
        "id": hashlib.sha1(_norm(title).encode()).hexdigest()[:16],
        "title": title,
        "url": url,
        "category": category,
        "source": source,
        "site": site,
        "published": published,   # ISO tarih (varsa)
    }


def _parse_feed(feed_url: str, category: str, source: str, limit: int,
                agent: str = UA, retries: int = 0) -> list[dict]:
    for deneme in range(retries + 1):
        feed = feedparser.parse(feed_url, agent=agent)
        status = getattr(feed, "status", None)
        if feed.entries or status in (200, 304):
            break
        # 429/503 vb. → feedparser hata vermeden boş döner; logla ve bekleyip tekrar dene
        print(f"  [{source}] boş yanıt (HTTP {status}), deneme {deneme + 1}/{retries + 1}")
        if deneme < retries:
            time.sleep(10 * (deneme + 1))
    items: list[dict] = []
    for e in feed.entries[:limit]:
        pub = None
        if getattr(e, "published_parsed", None):
            t = e.published_parsed
            pub = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
        site = getattr(getattr(e, "source", None), "title", None)  # Google News kaynak sitesi
        it = make_item(getattr(e, "title", ""), getattr(e, "link", ""),
                       category, source, pub, site)
        if it:
            items.append(it)
    return items


def fetch_google_news(src: dict) -> list[dict]:
    """Anahtar kelime başına bir Google News RSS sorgusu.

    'Görmediğim siteleri de görsün' ihtiyacının cevabı: sorguya takılan
    haber, takip listesinde olmayan bir sitede çıksa da yakalanır.
    """
    items: list[dict] = []
    hl = src.get("lang", "tr")
    params = {"tr": "hl=tr&gl=TR&ceid=TR:tr", "en": "hl=en-US&gl=US&ceid=US:en"}[hl]
    for kw in src.get("keywords", []):
        q = urllib.parse.quote(kw["q"])
        when = kw.get("when", "7d")   # son 7 gün
        url = f"https://news.google.com/rss/search?q={q}+when:{when}&{params}"
        items += _parse_feed(url, kw.get("category", "genel-bt"),
                             src["id"], kw.get("limit", 15), agent=GN_UA, retries=2)
        time.sleep(1.5)   # 40+ sorguyu tek seferde ateşlemeyelim
    return items


def fetch_rss(src: dict) -> list[dict]:
    """Takip edilen sitelerin kendi RSS'leri."""
    return _parse_feed(src["url"], src["category"], src["id"], src.get("limit", 20))


FETCHERS = {"google_news": fetch_google_news, "rss": fetch_rss}
