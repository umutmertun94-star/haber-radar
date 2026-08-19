"""Fable özet katmanı + Bülten okuma sayfası.

Filtreyi geçen haberlerin sayfası çekilir (trafilatura), Fable doğal dille
özet ve haber metni yazar. Paywall/çözülemeyen linkler başlıkta kalır.
Çıktılar: bültende özet satırı, docs/bulten/ altında okuma sayfası + arşiv,
docs/bulten/veri.json (Bülten v2 web uygulamasına beslenebilir format).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from pathlib import Path

import requests

from . import core

ROOT = Path(__file__).resolve().parent.parent
BULTEN_DIR = ROOT / "docs" / "bulten"
OZET_MODEL = os.environ.get("OZET_MODEL", "claude-fable-5")
MAX_OZET = 40          # haftalık üst sınır (maliyet emniyeti)
MIN_METIN = 400        # bundan kısa çekimler "içerik alınamadı" sayılır

OZET_PROMPT = """Bir merkez bankasının teknoloji birimi için haftalık bülten yazıyorsun.
Aşağıda bir haberin başlığı ve sayfasından çekilen ham metni var.

Kurallar:
- SADECE verilen içeriği kullan; içerikte olmayan hiçbir bilgi ekleme, varsayım yapma.
- Kurumsal, tarafsız ve resmî ama DOĞAL akan bir Türkçe kullan — bir insanın
  kaleme aldığı gibi. Kalıp girişler yasak ("...alanında önemli bir gelişme
  yaşandı", "son dönemde", "yapay zeka dünyasında" gibi doldurma ifadeler kullanma).
  Doğrudan olayın kendisiyle başla.
- Emoji, ünlem, pazarlama dili yok.
- Sadeleştirilmiş kurum dili: "mütalaa" değil "görüş", "mezkûr" değil "söz konusu".

SADECE şu JSON ile yanıt ver:
{"baslik_tr": "Türkçe başlık (haber dilinde, 8-14 kelime)",
 "ozet": "2-3 cümlelik özet — olay, aktör ve kurumsal önemi",
 "haber_metni": "150-250 kelimelik akıcı haber metni, 2 paragraf"}

BAŞLIK: {BASLIK}
İÇERİK:
{ICERIK}
"""


def _fetch_text(url: str) -> str | None:
    """Haber sayfasını çekip ana metni ayıklar; olmuyorsa None."""
    if not url or "news.google.com" in url:
        return None            # GN linkleri şifreli yönlendirme — çözülmüyor
    try:
        import trafilatura
        html = requests.get(url, timeout=25, headers={
            "User-Agent": "Mozilla/5.0 (compatible; haber-radar/1.0)"}).text
        text = trafilatura.extract(html) or ""
        return text if len(text) >= MIN_METIN else None
    except Exception:
        return None


def ozetle(items: list[dict]) -> list[dict]:
    """Filtreyi geçen haberlere Fable ile özet ekler (yerinde günceller)."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("[ozet] anahtar yok, atlanıyor")
        return items
    yapilan = 0
    for it in items:
        if yapilan >= MAX_OZET:
            break
        text = _fetch_text(it.get("url"))
        if not text:
            it["ozet_durum"] = "içerik alınamadı"
            continue
        prompt = OZET_PROMPT.replace("{BASLIK}", it["title"]).replace("{ICERIK}", text[:6000])
        try:
            r = requests.post(core.API_URL, timeout=120, headers={
                "x-api-key": key, "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }, json={"model": OZET_MODEL, "max_tokens": 1200,
                     "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            out = "".join(b.get("text", "") for b in r.json()["content"])
            data = json.loads(out.replace("```json", "").replace("```", "").strip())
            it["baslik_tr"] = data.get("baslik_tr")
            it["ozet"] = data.get("ozet")
            it["haber_metni"] = data.get("haber_metni")
            it["ozet_durum"] = "tam"
            yapilan += 1
        except Exception as ex:
            detail = getattr(getattr(ex, "response", None), "text", "") or ""
            print(f"[ozet] {it['title'][:40]}...: {ex} | {detail[:150]}")
            it["ozet_durum"] = "hata"
    print(f"[ozet] {yapilan} habere Fable özeti yazıldı ({OZET_MODEL})")
    return items


# ------------------------------------------------------------ Bülten sayfası
SAYFA = """<!doctype html>
<html lang="tr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bülten — __HAFTA__</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>
:root{--ink:#16273F;--paper:#F7F5F1;--accent:#8E2430;--mute:#66727F;--line:#E0DAD1}
*{box-sizing:border-box;margin:0}
body{background:var(--paper);color:var(--ink);font:17px/1.7 "IBM Plex Serif",serif}
header{border-bottom:3px double var(--ink);padding:34px 24px 22px}
.wrap{max-width:720px;margin:0 auto}
header h1{font:700 32px/1 "Space Grotesk",sans-serif;letter-spacing:.05em;text-transform:uppercase}
header .m{font:400 12.5px "IBM Plex Mono",monospace;color:var(--mute);margin-top:10px;display:flex;gap:18px;flex-wrap:wrap}
header a{color:var(--accent)}
main{padding:8px 24px 70px}
h2{font:700 14px "IBM Plex Mono",monospace;letter-spacing:.15em;text-transform:uppercase;
  color:var(--accent);margin:40px 0 6px;border-bottom:1px solid var(--line);padding-bottom:6px}
article{margin:26px 0}
article h3{font:600 20px/1.4 "IBM Plex Sans",sans-serif;margin-bottom:6px}
article h3 a{color:inherit;text-decoration:none}
article h3 a:hover{text-decoration:underline;text-decoration-color:var(--accent)}
article .kaynak{font:400 12px "IBM Plex Mono",monospace;color:var(--mute);margin-bottom:8px}
article p{margin:8px 0}
details{margin-top:6px}
summary{font:400 13px "IBM Plex Mono",monospace;color:var(--accent);cursor:pointer}
details p{font-size:16px}
.sadece-baslik .kaynak::after{content:" · yalnızca başlık"}
</style></head><body>
<header><div class="wrap">
  <h1>Bülten</h1>
  <div class="m"><span>__HAFTA__</span><span>__SAYI__ haber</span>
  <span><a href="../index.html">← Radar</a></span><span>__ARSIV__</span></div>
</div></header>
<main class="wrap">__GOVDE__</main>
</body></html>
"""


def _madde(it: dict) -> str:
    baslik = it.get("baslik_tr") or it["title"]
    src = it.get("site") or it.get("source", "")
    tam = it.get("ozet_durum") == "tam"
    parcalar = [f'<article class="{"" if tam else "sadece-baslik"}">',
                f'<h3><a href="{it["url"]}" target="_blank" rel="noopener">{baslik}</a></h3>',
                f'<div class="kaynak">{src} · {it.get("published") or it.get("first_seen","")}</div>']
    if tam:
        parcalar.append(f"<p>{it['ozet']}</p>")
        if it.get("haber_metni"):
            metin = "".join(f"<p>{p.strip()}</p>" for p in it["haber_metni"].split("\n") if p.strip())
            parcalar.append(f"<details><summary>haberin tamamı</summary>{metin}</details>")
    parcalar.append("</article>")
    return "\n".join(parcalar)


def bulten_sayfasi(items: list[dict]) -> Path:
    BULTEN_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today(); yil, hafta, _ = today.isocalendar()
    etiket = f"{yil} · {hafta}. hafta"
    govde = []
    for cat, label in core.CATEGORY_LABELS.items():
        grup = [i for i in items if i["category"] == cat]
        if not grup:
            continue
        govde.append(f"<h2>{label}</h2>")
        govde += [_madde(i) for i in sorted(grup, key=lambda x: -(x.get("relevance") or 5))]
    arsiv_adi = f"arsiv-{yil}-H{hafta:02d}.html"
    eski = sorted(BULTEN_DIR.glob("arsiv-*.html"), reverse=True)[:8]
    arsiv_link = " ".join(f'<a href="{p.name}">{re.sub(r"arsiv-|.html","",p.name)}</a>' for p in eski) or "arşiv boş"
    html = (SAYFA.replace("__HAFTA__", etiket).replace("__SAYI__", str(len(items)))
                 .replace("__GOVDE__", "\n".join(govde) or "<p>Bu hafta bülteni geçen haber yok.</p>")
                 .replace("__ARSIV__", "arşiv: " + arsiv_link))
    out = BULTEN_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    (BULTEN_DIR / arsiv_adi).write_text(html, encoding="utf-8")
    (BULTEN_DIR / "veri.json").write_text(json.dumps([
        {"baslik": i.get("baslik_tr") or i["title"], "ozet": i.get("ozet"),
         "haber_metni": i.get("haber_metni"), "kaynak": i.get("site") or i.get("source"),
         "url": i["url"], "kategori": i["category"]} for i in items],
        ensure_ascii=False, indent=1), encoding="utf-8")
    return out
