"""Dashboard üretici + ana orkestratör.  Kullanım: python -m radar.run"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import yaml

from . import core
from .fetchers import FETCHERS

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

TEMPLATE = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Haber Radarı</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--ink:#16273F;--paper:#F4F2EF;--card:#fff;--accent:#8E2430;--mute:#66727F;--line:#DDD8D0}
*{box-sizing:border-box;margin:0}
body{background:var(--paper);color:var(--ink);font:16px/1.55 "IBM Plex Sans",sans-serif}
header{background:var(--accent);color:#fff;padding:28px 24px}
.wrap{max-width:880px;margin:0 auto}
header h1{font:700 26px/1.1 "Space Grotesk",sans-serif;letter-spacing:.04em;text-transform:uppercase}
header .stamp{font:400 12px/1 "IBM Plex Mono",monospace;opacity:.75;margin-top:8px}
.filters{display:flex;flex-wrap:wrap;gap:8px;padding:18px 24px}
.chip{border:1px solid var(--line);background:var(--card);border-radius:999px;padding:5px 14px;
  font:400 13px "IBM Plex Mono",monospace;cursor:pointer;color:var(--mute)}
.chip.on{background:var(--ink);border-color:var(--ink);color:#fff}
main{padding:0 24px 64px}
.day{margin-top:30px}
.day h2{font:500 13px "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;
  color:var(--mute);border-bottom:1px solid var(--line);padding-bottom:8px}
.item{padding:14px 0;border-bottom:1px solid var(--line)}
.item h3{font:600 16.5px/1.4 "IBM Plex Sans",sans-serif}
.item h3 a{color:inherit;text-decoration:none}
.item h3 a:hover{text-decoration:underline;text-decoration-color:var(--accent)}
.meta{margin-top:4px;font:400 12.5px "IBM Plex Mono",monospace;color:var(--mute);display:flex;gap:14px;flex-wrap:wrap}
.rel{color:var(--accent)}
.empty{margin-top:48px;color:var(--mute);font-style:italic}
</style></head>
<body>
<header><div class="wrap"><h1>Haber Radarı</h1>
<div class="stamp">son tarama: __UPDATED__ · haftalık otomatik tarama</div></div></header>
<div class="wrap"><nav class="filters" id="filters"></nav><main id="list"></main></div>
<script>
const ITEMS=__ITEMS_JSON__;
const LABELS=__LABELS_JSON__;
let cat="hepsi";
function render(){
  const f=document.getElementById("filters");f.innerHTML="";
  ["hepsi",...new Set(ITEMS.map(i=>i.category))].forEach(c=>{
    const b=document.createElement("button");b.className="chip"+(cat===c?" on":"");
    b.textContent=c==="hepsi"?"Tümü":(LABELS[c]||c);b.onclick=()=>{cat=c;render()};f.appendChild(b);});
  let items=cat==="hepsi"?ITEMS:ITEMS.filter(i=>i.category===cat);
  items=[...items].sort((a,b)=>(b.first_seen||"").localeCompare(a.first_seen||"")||(b.relevance||0)-(a.relevance||0));
  const list=document.getElementById("list");list.innerHTML="";
  if(!items.length){list.innerHTML='<p class="empty">Henüz haber yok — ilk tarama sonrası dolacak.</p>';return}
  let cur="";
  items.forEach(i=>{
    if(i.first_seen!==cur){cur=i.first_seen;
      const h=document.createElement("section");h.className="day";h.id="d"+cur;
      h.innerHTML=`<h2>${cur} taraması</h2>`;list.appendChild(h);}
    const d=document.createElement("article");d.className="item";
    const rel=i.relevance!=null?`<span class="rel">önem ${i.relevance}/10</span>`:"";
    d.innerHTML=`<h3><a href="${i.url}" target="_blank" rel="noopener">${i.title}</a></h3>
      <div class="meta"><span>${LABELS[i.category]||i.category}</span><span>${i.site||i.source}</span>${rel}</div>`;
    document.getElementById("d"+cur).appendChild(d);});
}
render();
</script></body></html>
"""


def write_dashboard(items: dict[str, dict]) -> Path:
    DOCS.mkdir(parents=True, exist_ok=True)
    shown = [i for i in items.values()
             if (i.get("relevance") is None or i["relevance"] >= core.THRESHOLD)]
    html = (TEMPLATE
            .replace("__ITEMS_JSON__", json.dumps(shown, ensure_ascii=False))
            .replace("__LABELS_JSON__", json.dumps(core.CATEGORY_LABELS, ensure_ascii=False))
            .replace("__UPDATED__", dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
    out = DOCS / "index.html"
    out.write_text(html, encoding="utf-8")
    (DOCS / "news.json").write_text(  # mevcut bülten uygulamasına beslenebilir
        json.dumps(shown, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> int:
    cfg = yaml.safe_load((ROOT / "sources.yaml").read_text(encoding="utf-8"))
    existing = core.load()
    all_new: list[dict] = []
    for src in cfg["sources"]:
        if not src.get("enabled", True):
            continue
        fetcher = FETCHERS.get(src["type"])
        if not fetcher:
            print(f"[{src['id']}] bilinmeyen tür"); continue
        try:
            fetched = fetcher(src)
        except Exception as ex:
            print(f"[{src['id']}] HATA: {ex}"); continue
        new = core.merge(existing, fetched)
        all_new += new
        print(f"[{src['id']}] {len(fetched)} haber tarandı, {len(new)} yeni")

    filtered = core.llm_filter(all_new)
    # eşiği geçemeyenler depodan da düşsün ki dashboard temiz kalsın
    dropped = {i["id"] for i in all_new} - {i["id"] for i in filtered}
    for did in dropped:
        existing.pop(did, None)
    core.save(existing)

    path, body = core.write_bulletin(filtered)
    write_dashboard(existing)
    if filtered:
        yr, wk, _ = dt.date.today().isocalendar()
        core.send_email(f"Haber Radarı — {yr}/{wk}. hafta ({len(filtered)} haber)", body)
    print(f"\n{len(filtered)} haber bültende → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
