"""Depolama + Anthropic API filtre/özet katmanı + bülten + e-posta."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "items.json"
OUT_DIR = ROOT / "output"

CATEGORY_LABELS = {
    "yapay-zeka": "Yapay Zeka",
    "siber-guvenlik": "Siber Güvenlik",
    "kuantum": "Kuantum",
    "veri-merkezi": "Veri Merkezi",
    "ai-governance": "AI Governance",
    "merkez-bankaciligi": "Merkez Bankacılığı / Ödeme Sistemleri",
    "is-surekliligi": "İş Sürekliliği",
    "turkiye": "Türkiye",
    "genel-bt": "Genel BT",
}

# ------------------------------------------------------------------ depo
def load() -> dict[str, dict]:
    if DATA_FILE.exists():
        return {i["id"]: i for i in json.loads(DATA_FILE.read_text(encoding="utf-8"))}
    return {}


def save(items: dict[str, dict], keep_days: int = 45) -> None:
    cutoff = (dt.date.today() - dt.timedelta(days=keep_days)).isoformat()
    kept = [i for i in items.values() if (i.get("first_seen") or "9999") >= cutoff]
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(
        sorted(kept, key=lambda x: x.get("first_seen") or "", reverse=True),
        ensure_ascii=False, indent=1), encoding="utf-8")


def _anahtar(it: dict) -> str:
    """Kaynak ekinden arındırılmış, karşılaştırmaya uygun başlık.

    Google News başlıkları " - Site Adı" ile biter. Aynı haber hem sitenin
    kendi RSS'inden hem Google News'ten gelince bu ek yüzünden farklı
    görünüyordu (ör. IDEMIA/KT haberi üç kez girdi).
    """
    t = it.get("title") or ""
    site = it.get("site") or ""
    if site and t.endswith(" - " + site):
        t = t[: -len(site) - 3]
    elif " - " in t and it.get("source", "").startswith("gnews"):
        t = t.rsplit(" - ", 1)[0]
    return re.sub(r"[^\w]+", " ", t.lower()).strip()


def merge(existing: dict[str, dict], fetched: list[dict]) -> list[dict]:
    today = dt.date.today().isoformat()
    gorulen = {_anahtar(i) for i in existing.values()}
    new = []
    for it in fetched:
        if it["id"] in existing:
            continue
        k = _anahtar(it)
        if k and k in gorulen:
            continue
        gorulen.add(k)
        it["first_seen"] = today
        existing[it["id"]] = it
        new.append(it)
    return new


# ------------------------------------------- Anthropic API: filtre + özet
API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
BATCH = 25
THRESHOLD = 6

PROMPT_BASE = """Bir merkez bankasının Yenilikçi Teknolojiler birimi için haftalık haber taraması yapıyorsun.
Editörün seçim çizgisi (gerçek seçim geçmişinden çıkarılmıştır):

1. ÖZNE HİYERARŞİSİ belirleyicidir: haberin öznesi bir merkez bankası, finansal
   düzenleyici veya uluslararası kuruluşsa (BIS, IMF, ECB, Fed, BoE, MAS, RBI,
   FSB, EBA/ESMA, G7...) puan yüksektir.
2. centralbanking.com kaynaklı yapay zeka içeriği HER ZAMAN 8+ puan alır — editör
   bu kaynaktan AI içeriği kaçırmak istemiyor.
3. Türkiye teknoloji/kamu haberleri (yerli AI, TÜBİTAK, SSB, kuantum, siber
   düzenleme) yüksek puan alır.
4. Düzenleme/yönetişim haberleri (AI Act, çerçeveler, denetim, yasalar) yüksek puan alır.
5. Büyük teknoloji şirketi haberleri YALNIZCA kurumsal/finansal/güvenlik sonucu
   varsa girer (model güvenliği, düzenleyici etki, finans sektörü bağlantısı,
   büyük yapısal kırılma). Ürün lansmanı, tüketici özelliği, uygulama güncellemesi,
   şirket magazini DÜŞÜK puan alır.
6. Siber güvenlik: finansal sisteme/kurumlara dokunan olay ve politikalar yüksek.
   İSTİSNA: internetin temel altyapısını etkileyen KRİTİK açıklar (PHP, OpenSSL,
   Apache, nginx, Linux çekirdeği, yaygın VPN/güvenlik duvarı ürünleri gibi)
   aktif istismar, acil yama, CISA/NSA/ulusal CERT uyarısı ya da kitlesel etki
   varsa 8+ puan alır. Bunlar her kurumun BT ekibini doğrudan ilgilendirir.
   Rutin CVE duyuruları, tek ürünlü sıradan yamalar ve tüketici güvenliği düşük.
7. Kuantum: politika, finans sektörü etkisi ve PQC yüksek; salt donanım/akademik
   ilerleme orta.
8. Veri merkezi: yatırım/enerji magazini düşük; politika ve düzenleme boyutu varsa orta.
9. Teknoloji dünyasının gündemini belirleyen büyük olaylar (küresel çaplı kesinti,
   büyük bulut/CDN arızası, kritik altyapı açığı, sektörü etkileyen büyük ihlal)
   finansla doğrudan bağlantısı olmasa da 8+ puan alır.

{ORNEKLER}
Aşağıdaki başlıkları değerlendir:
- relevance: 0-10 (yukarıdaki çizgiye göre)
- dup_of: bu başlık AYNI OLAYI anlatan başka bir başlığın kopyasıysa onun numarası,
  değilse null. İki durumu da kontrol et:
  (a) aşağıdaki listede daha önceki bir başlık → o başlığın numarası (ör. 3)
  (b) "BU HAFTA ZATEN BÜLTENDE" listesindeki bir başlık → "E" + numara (ör. "E12")
  Aynı olayın farklı sitelerde, farklı dillerde ya da farklı günlerde çıkan
  haberleri kopyadır. Aynı konudaki FARKLI gelişmeler kopya değildir.

SADECE şu JSON ile yanıt ver:
{{"results": [{{"i": 0, "relevance": 8, "dup_of": null}}, ...]}}

Başlıklar:
"""

ORNEK_DOSYA = ROOT / "data" / "ornek-secimler.md"


def _prompt() -> str:
    ornek = ""
    if ORNEK_DOSYA.exists():
        ornek = ("GERÇEK ÖRNEKLER (editörün geçmiş kararları):\n"
                 + ORNEK_DOSYA.read_text(encoding="utf-8") + "\n")
    return PROMPT_BASE.format(ORNEKLER=ornek)


BAGLAM_MAX = 150   # filtreye bağlam olarak verilecek en fazla önceki başlık


def llm_filter(items: list[dict], onceki: list[str] | None = None) -> list[dict]:
    """ANTHROPIC_API_KEY tanımlıysa puanla + mükerrer ele; yoksa hepsi geçer.

    onceki: bu hafta daha önce bültene girmiş başlıklar. Her partiye bağlam
    olarak verilir, önceki partilerde geçenler de listeye eklenir. Böylece
    kopyalar parti ve koşu sınırını aşınca da yakalanır.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not items:
        return items
    model = os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    baglam: list[str] = list(onceki or [])
    kept: list[dict] = []
    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        listing = "\n".join(f'{j}. [{it["category"]}] {it["title"]} ({it.get("site") or it["source"]})'
                            for j, it in enumerate(batch))
        if baglam:
            son = baglam[-BAGLAM_MAX:]
            listing += ("\n\nBU HAFTA ZATEN BÜLTENDE (puanlama, sadece kopya kontrolü için):\n"
                        + "\n".join(f"E{k}. {t}" for k, t in enumerate(son)))
        try:
            r = requests.post(API_URL, timeout=90, headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }, json={
                "model": model, "max_tokens": 2000,
                "messages": [{"role": "user", "content": _prompt() + listing}],
            })
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json()["content"])
            text = text.replace("```json", "").replace("```", "").strip()
            start = text.find("{")
            data, _ = json.JSONDecoder().raw_decode(text[start:])
            scores = {x["i"]: x for x in data["results"]}
        except Exception as ex:
            detail = getattr(getattr(ex, "response", None), "text", "") or ""
            print(f"[llm] hata, parti filtrelenmeden geçiyor: {ex} | detay: {detail[:300]}")
            kept += batch
            continue
        kopya = 0
        for j, it in enumerate(batch):
            s = scores.get(j, {})
            it["relevance"] = s.get("relevance")
            d = s.get("dup_of")
            if d is not None and d != j:
                kopya += 1
                continue
            if s.get("relevance", 10) >= THRESHOLD:
                kept.append(it)
                baglam.append(it["title"])
        if kopya:
            print(f"[llm] parti {i // BATCH + 1}: {kopya} kopya elendi")
    print(f"[llm] {len(items)} haberden {len(kept)} tanesi bültene girdi")
    return kept


# ---------------------------------------------------------------- bülten
def write_bulletin(new_items: list[dict]) -> tuple[Path, str]:
    today = dt.date.today()
    year, week, _ = today.isocalendar()
    path = OUT_DIR / f"bulten-{year}-H{week:02d}.md"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"# Haber Radarı — {year} / {week}. Hafta", ""]
    ordered = sorted(new_items, key=lambda x: -(x.get("relevance") or 5))
    for cat, label in CATEGORY_LABELS.items():
        group = [i for i in ordered if i["category"] == cat]
        if not group:
            continue
        lines.append(f"## {label}")
        for it in group:
            src = it.get("site") or it["source"]
            date = it.get("published") or it.get("first_seen") or ""
            baslik = it.get("baslik_tr") or it["title"]
            lines.append(f"- [{baslik}]({it['url']}) — {src}, {date}")
            if it.get("ozet"):
                lines.append(f"  - {it['ozet']}")
        lines.append("")
    if len(lines) == 2:
        lines.append("Bu hafta eşiği geçen haber bulunamadı.")
    body = "\n".join(lines)
    path.write_text(body, encoding="utf-8")
    return path, body


# --------------------------------------------------------------- e-posta
def send_email(subject: str, markdown_body: str) -> None:
    """SMTP secrets tanımlıysa bülteni e-postayla gönderir, yoksa atlar.

    Gerekli secrets: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO
    (Gmail için: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, uygulama şifresi)
    """
    host = os.environ.get("SMTP_HOST")
    if not host:
        print("[eposta] SMTP tanımlı değil, atlanıyor")
        return
    msg = MIMEText(markdown_body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = os.environ["SMTP_USER"]
    msg["To"] = os.environ["MAIL_TO"]
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", 587))) as s:
            s.starttls()
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            s.send_message(msg)
        print(f"[eposta] gönderildi → {os.environ['MAIL_TO']}")
    except Exception as ex:
        print(f"[eposta] gönderilemedi: {ex}")
