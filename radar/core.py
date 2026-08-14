"""Depolama + Anthropic API filtre/özet katmanı + bülten + e-posta."""
from __future__ import annotations

import datetime as dt
import json
import os
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


def merge(existing: dict[str, dict], fetched: list[dict]) -> list[dict]:
    today = dt.date.today().isoformat()
    new = []
    for it in fetched:
        if it["id"] in existing:
            continue
        it["first_seen"] = today
        existing[it["id"]] = it
        new.append(it)
    return new


# ------------------------------------------- Anthropic API: filtre + özet
API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5"
BATCH = 25
THRESHOLD = 6

PROMPT = """Bir merkez bankasının Yenilikçi Teknolojiler birimi için haftalık haber taraması yapıyorsun.
İlgi alanları: yapay zeka, AI governance, siber güvenlik, kuantum/post-kuantum kriptografi,
veri merkezleri, ödeme sistemleri/CBDC, iş sürekliliği, Türkiye teknoloji gündemi, kurumsal BT.

Aşağıdaki başlıkları değerlendir:
- relevance: 0-10 (kurum gündemi için önem; magazin/ürün reklamı/spekülasyon düşük)
- dup_of: bu başlık listedeki daha önceki bir başlıkla AYNI OLAYI anlatıyorsa o başlığın
  numarası, değilse null (aynı olayın farklı sitelerdeki kopyaları elensin)

SADECE şu JSON ile yanıt ver:
{"results": [{"i": 0, "relevance": 8, "dup_of": null}, ...]}

Başlıklar:
"""


def llm_filter(items: list[dict]) -> list[dict]:
    """ANTHROPIC_API_KEY tanımlıysa puanla + mükerrer ele; yoksa hepsi geçer."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not items:
        return items
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    kept: list[dict] = []
    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        listing = "\n".join(f'{j}. [{it["category"]}] {it["title"]} ({it.get("site") or it["source"]})'
                            for j, it in enumerate(batch))
        try:
            r = requests.post(API_URL, timeout=90, headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }, json={
                "model": model, "max_tokens": 2000,
                "messages": [{"role": "user", "content": PROMPT + listing}],
            })
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json()["content"])
            text = text.replace("```json", "").replace("```", "").strip()
            scores = {x["i"]: x for x in json.loads(text)["results"]}
        except Exception as ex:
            print(f"[llm] hata, parti filtrelenmeden geçiyor: {ex}")
            kept += batch
            continue
        for j, it in enumerate(batch):
            s = scores.get(j, {})
            it["relevance"] = s.get("relevance")
            if s.get("dup_of") is not None:
                continue
            if s.get("relevance", 10) >= THRESHOLD:
                kept.append(it)
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
            lines.append(f"- [{it['title']}]({it['url']}) — {src}, {date}")
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
