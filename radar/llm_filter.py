"""Faz 2: Anthropic API ile ilgililik filtresi.

Keşif katmanından (DDG, Alerts) gelen ham ipuçlarını merkez bankası
BT gündemi açısından puanlar; düşük puanlıları bültene sokmaz.

Etkinleştirme: ANTHROPIC_API_KEY tanımlıysa çalışır, yoksa sessizce
atlanır. GitHub Actions'ta: Settings → Secrets → ANTHROPIC_API_KEY.
Model: ANTHROPIC_MODEL değişkeni (varsayılan: claude-haiku-4-5).
haber-radar ile aynı anahtar kullanılabilir.
"""
from __future__ import annotations

import json
import os

import requests

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
BATCH = 15
THRESHOLD = 6

PROMPT = """Bir merkez bankasının Yenilikçi Teknolojiler birimi için etkinlik tarıyorsun.
İlgi alanları: yapay zeka, AI governance, siber güvenlik, kuantum/post-kuantum kriptografi,
veri merkezleri, ödeme sistemleri/CBDC, genel kurumsal BT.

KURALLAR:
- Online etkinlik/webinar: dünyanın her yerinden olabilir, konu ilgiliyse yüksek puan.
- Yüz yüze etkinlik: SADECE Türkiye'deyse ilgilidir. Türkiye dışındaki yüz yüze
  etkinliklere en fazla 3 puan ver (katılım imkânı yok).
- Kayıt/katılım sayfası olan gerçek etkinlik duyuruları aranıyor; haber makalesi,
  ürün sayfası, geçmiş etkinlik özeti, etkinlik listesi makaleleri düşük puan alır.

Her sonuç için:
- relevance: 0-10
- is_event: sayfa gerçekten yaklaşan bir etkinliğin duyurusu mu (true/false)
- start_date: başlık/özette etkinlik tarihi AÇIKÇA varsa "YYYY-MM-DD", yoksa null
  (tahmin etme; sadece metinde geçen tarihi yaz)
- online: webinar/online olduğu belliyse true, yüz yüze olduğu belliyse false, belirsizse null

SADECE şu JSON formatında yanıt ver, başka hiçbir şey yazma:
{"results": [{"i": 0, "relevance": 8, "is_event": true, "start_date": "2026-09-15", "online": true}, ...]}

Sonuçlar:
"""


def _enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def score_leads(leads: list[dict]) -> list[dict]:
    """İpuçlarını puanlar; eşiği geçenleri döner. Anahtar yoksa hepsi geçer."""
    if not _enabled() or not leads:
        return leads

    key = os.environ["ANTHROPIC_API_KEY"]
    model = os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    kept: list[dict] = []

    for i in range(0, len(leads), BATCH):
        batch = leads[i:i + BATCH]
        items = "\n".join(
            f'{j}. {e["title"]} — {e.get("extra", {}).get("snippet", "")[:150]} ({e["url"]})'
            for j, e in enumerate(batch)
        )
        try:
            r = requests.post(API_URL, timeout=90, headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }, json={
                "model": model, "max_tokens": 1500,
                "messages": [{"role": "user", "content": PROMPT + items}],
            })
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json()["content"])
            text = text.replace("```json", "").replace("```", "").strip()
            scores = {x["i"]: x for x in json.loads(text)["results"]}
        except Exception as ex:
            detail = getattr(getattr(ex, "response", None), "text", "") or ""
            print(f"[llm-filtre] hata, bu parti filtrelenmeden geçiyor: {ex} | detay: {detail[:300]}")
            kept += batch
            continue

        for j, e in enumerate(batch):
            s = scores.get(j, {})
            e.setdefault("extra", {})["llm_relevance"] = s.get("relevance")
            if s.get("relevance", 10) >= THRESHOLD and s.get("is_event", True):
                # tarih çıkarılabildiyse ipucu dashboard'a terfi eder
                if s.get("start_date") and not e.get("start_date"):
                    e["start_date"] = s["start_date"]
                    e["needs_review"] = False
                    e["extra"]["llm_extracted"] = True
                if s.get("online") is not None and e.get("online") is None:
                    e["online"] = s["online"]
                kept.append(e)

    print(f"[llm-filtre] {len(leads)} ipucundan {len(kept)} tanesi eşiği geçti")
    return kept
