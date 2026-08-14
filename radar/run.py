"""Ana orkestratör: kaynakları tara → birleştir → bülten + dashboard üret.

Kullanım:
    python -m radar.run                 # tüm etkin kaynaklar
    python -m radar.run --only confstech,ddg   # seçili kaynaklar
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import store
from .bulletin import write_bulletin
from .dashboard import write_dashboard
from .fetchers import FETCHERS

SOURCES_FILE = Path(__file__).resolve().parent.parent / "sources.yaml"


def _rule_ok(e: dict, rules: dict) -> bool:
    """Yüz yüze etkinlik yalnızca izinli ülkelerdeyse geçer; online serbest."""
    if e.get("source") in rules.get("istisna_kaynaklar", []):
        return True
    if e.get("online") is not False:      # online veya bilinmiyor → geçer
        return True
    ulkeler = {u.lower() for u in rules.get("yuz_yuze_ulkeler", [])}
    country = (e.get("country") or "").lower()
    return country in ulkeler if country else False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="virgülle ayrılmış kaynak id listesi")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None

    cfg = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))
    rules = cfg.get("rules", {})
    existing = store.load()
    # kural değişikliği geçmişe de işlesin: depodaki aykırı kayıtları temizle
    for eid in [k for k, e in existing.items() if not _rule_ok(e, rules)]:
        del existing[eid]
    all_new: list[dict] = []

    for src in cfg["sources"]:
        if not src.get("enabled", True):
            continue
        if only and src["id"] not in only:
            continue
        fetcher = FETCHERS.get(src["type"])
        if not fetcher:
            print(f"[{src['id']}] bilinmeyen tür: {src['type']}")
            continue
        try:
            fetched = fetcher(src)
        except Exception as ex:
            print(f"[{src['id']}] HATA: {ex}")
            continue
        fetched = [ev for ev in fetched
                   if _rule_ok(ev.to_dict(), rules)]
        new = store.merge(existing, fetched)
        all_new += new
        print(f"[{src['id']}] {len(fetched)} kayıt tarandı, {len(new)} yeni")

    # Faz 2: ipuçlarını LLM ile ele/terfi ettir — kayıttan ÖNCE ki
    # çıkarılan tarihler depoya ve dashboard'a işlensin
    from .llm_filter import score_leads
    leads = [e for e in all_new if e.get("needs_review")]
    confirmed = [e for e in all_new if not e.get("needs_review")]
    passed = score_leads(leads)
    # eşiği geçemeyen ipuçları depoda gürültü olarak kalmasın
    for e in leads:
        if e not in passed:
            existing.pop(e["id"], None)
    all_new = confirmed + passed

    store.prune(existing)
    store.save(existing)

    b = write_bulletin(all_new, existing)
    d = write_dashboard(existing)
    print(f"\nToplam: {len(existing)} etkinlik kayıtta, {len(all_new)} yeni")
    print(f"Bülten:    {b}")
    print(f"Dashboard: {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
