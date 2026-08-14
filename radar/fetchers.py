"""Kaynak türlerine göre etkinlik çekiciler.

Her fetcher sources.yaml'daki bir kaynak tanımını alır ve Event listesi döner.
Yeni kaynak türü eklemek = buraya bir fonksiyon + FETCHERS sözlüğüne kayıt.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import requests
from bs4 import BeautifulSoup

from .models import Event

UA = {"User-Agent": "etkinlik-radar/0.1 (+https://github.com/)"}
TIMEOUT = 30


def _get(url: str) -> requests.Response:
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- confs.tech
CONFSTECH_RAW = (
    "https://raw.githubusercontent.com/tech-conferences/"
    "conference-data/main/conferences/{year}/{topic}.json"
)


def fetch_confstech(src: dict) -> list[Event]:
    """confs.tech açık veritabanı (GitHub'daki JSON dosyaları)."""
    events: list[Event] = []
    year = dt.date.today().year
    for y in (year, year + 1):
        for topic in src.get("topics", []):
            try:
                data = _get(CONFSTECH_RAW.format(year=y, topic=topic)).json()
            except Exception:
                continue  # o yıl/konu dosyası henüz yoksa sorun değil
            for item in data:
                events.append(Event(
                    title=item.get("name", "").strip(),
                    url=item.get("url", ""),
                    category=src.get("category_map", {}).get(topic, src["category"]),
                    source=src["id"],
                    start_date=item.get("startDate"),
                    end_date=item.get("endDate"),
                    city=item.get("city"),
                    country=item.get("country"),
                    online=bool(item.get("online")) if "online" in item else None,
                ))
    return events


# --------------------------------------------------------------------- RSS
def fetch_rss(src: dict) -> list[Event]:
    """RSS/Atom kaynakları — Google Alerts dahil.

    Alerts girdileri etkinliğin kendisi değil 'ipucu'dur: tarih alanı boş
    bırakılır ve needs_review=True işaretlenir; bültende ayrı bölümde çıkar.
    """
    import feedparser

    feed = feedparser.parse(src["url"])
    events: list[Event] = []
    for e in feed.entries[: src.get("limit", 25)]:
        title = re.sub(r"<[^>]+>", "", getattr(e, "title", "")).strip()
        link = getattr(e, "link", "")
        if not title or not link:
            continue
        events.append(Event(
            title=title,
            url=link,
            category=src["category"],
            source=src["id"],
            needs_review=src.get("needs_review", True),
        ))
    return events


# -------------------------------------------------------- genel HTML kazıma
def fetch_html(src: dict) -> list[Event]:
    """Konfigürasyonla yönetilen genel HTML kazıyıcı.

    sources.yaml'da her kaynak için CSS seçicileri tanımlanır:
      selectors:
        item: ".event-card"
        title: "h3"
        link: "a"          # href alınır
        date: ".date"      # opsiyonel, ham metin olarak saklanır
    """
    sel = src["selectors"]
    soup = BeautifulSoup(_get(src["url"]).text, "html.parser")
    events: list[Event] = []
    for node in soup.select(sel["item"])[: src.get("limit", 40)]:
        t = node.select_one(sel["title"])
        a = node.select_one(sel.get("link", "a"))
        if not t or not a or not a.get("href"):
            continue
        url = requests.compat.urljoin(src["url"], a["href"])
        date_raw = None
        if sel.get("date"):
            d = node.select_one(sel["date"])
            date_raw = d.get_text(" ", strip=True) if d else None
        events.append(Event(
            title=t.get_text(" ", strip=True),
            url=url,
            category=src["category"],
            source=src["id"],
            needs_review=True,
            extra={"date_raw": date_raw} if date_raw else {},
        ))
    return events


# ------------------------------------------------------- DuckDuckGo keşfi
def fetch_ddg(src: dict) -> list[Event]:
    """Anahtar gerektirmeyen arama keşfi (ddgs kütüphanesi).

    Sabit havuzun dışındaki etkinlikleri yakalamak için haftalık sorgular.
    Sonuçlar 'ipucu' niteliğindedir: needs_review=True.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # eski paket adı
        except ImportError:
            print(f"[{src['id']}] ddgs kurulu değil, atlanıyor")
            return []

    events: list[Event] = []
    with DDGS() as ddgs:
        for q in src.get("queries", []):
            try:
                results = list(ddgs.text(q["q"], max_results=q.get("max", 8)))
            except Exception as ex:
                print(f"[{src['id']}] sorgu hatası ({q['q']}): {ex}")
                continue
            for r in results:
                events.append(Event(
                    title=r.get("title", "").strip(),
                    url=r.get("href", ""),
                    category=q.get("category", src.get("category", "genel-bt")),
                    source=src["id"],
                    needs_review=True,
                    extra={"query": q["q"], "snippet": r.get("body", "")[:200]},
                ))
    return events


# ------------------------------------------------- çekirdek (elle) liste
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """Ayın n. haftaiçi günü (weekday: 0=Pzt ... 6=Paz)."""
    d = dt.date(year, month, 1)
    return d + dt.timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))


def fetch_manual(src: dict) -> list[Event]:
    """sources.yaml içinde elle tutulan çapa etkinlikler (GITEX, MWC vb.).

    Kaçırılması kabul edilemez büyük etkinlikler keşif katmanına
    bırakılmaz; bu listede durur ve dashboard/bültene doğrudan girer.

    Tekrarlayan seriler (ör. TRAI Meet-Up: her ayın 3. çarşambası) için
    tarih yerine recurring alanı verilir; gelecek tarihler hesaplanır:
      recurring: {weekday: 2, ordinal: 3, months_ahead: 3}
    """
    events: list[Event] = []
    today = dt.date.today()
    for item in src.get("events", []):
        rec = item.get("recurring")
        if rec:
            y, m = today.year, today.month
            for _ in range(rec.get("months_ahead", 3) + 1):
                d = _nth_weekday(y, m, rec.get("weekday", 2), rec.get("ordinal", 3))
                if d >= today:
                    events.append(Event(
                        title=item["title"], url=item["url"],
                        category=item.get("category", "genel-bt"),
                        source=src["id"], start_date=d.isoformat(),
                        city=item.get("city"), country=item.get("country"),
                        online=item.get("online"),
                    ))
                m += 1
                if m > 12:
                    m, y = 1, y + 1
            continue
        events.append(Event(
            title=item["title"],
            url=item["url"],
            category=item.get("category", "genel-bt"),
            source=src["id"],
            start_date=item.get("start_date"),
            end_date=item.get("end_date"),
            city=item.get("city"),
            country=item.get("country"),
            online=item.get("online"),
        ))
    return events


# ------------------------------------------------------------ kommunity
def fetch_kommunity(src: dict) -> list[Event]:
    """kommunity.com toplulukları (TRAI vb. Türkiye teknoloji meetupları).

    Sitenin kendi API ucunu kullanır; şema değişirse loglardan görülür,
    alanlar savunmacı okunur.
    """
    events: list[Event] = []
    for slug in src.get("communities", []):
        url = f"https://api.kommunity.com/api/v1/{slug}/events?page=1"
        try:
            data = _get(url).json()
        except Exception as ex:
            print(f"[{src['id']}] {slug}: erişilemedi ({ex})")
            continue
        items = data.get("data") or data.get("events") or []
        if not items:
            print(f"[{src['id']}] {slug}: kayıt gelmedi (şema kontrolü gerekebilir)")
        for it in items:
            title = it.get("name") or it.get("title") or ""
            eslug = it.get("slug") or ""
            eurl = it.get("detail_url") or (
                f"https://kommunity.com/{slug}/events/{eslug}" if eslug else "")
            sd = it.get("start_date")
            if isinstance(sd, dict):
                sd = sd.get("date") or sd.get("iso") or None
            if isinstance(sd, str):
                sd = sd[:10]
            venue = (it.get("venue") or {}) if isinstance(it.get("venue"), dict) else {}
            online = it.get("is_online")
            events.append(Event(
                title=title, url=eurl,
                category=src.get("category", "genel-bt"),
                source=src["id"],
                start_date=sd,
                city=venue.get("city") or "İstanbul/Ankara?",
                country="Türkiye",
                online=bool(online) if online is not None else None,
                needs_review=sd is None,
            ))
    return events


FETCHERS = {
    "kommunity": fetch_kommunity,
    "manual": fetch_manual,
    "confstech": fetch_confstech,
    "rss": fetch_rss,
    "html": fetch_html,
    "ddg": fetch_ddg,
}
