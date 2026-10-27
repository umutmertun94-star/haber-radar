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
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:0 24px 12px}
.row .lbl{font:500 11px "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--mute);margin-right:4px}
.filters.row{padding-top:18px}
.chip .n{opacity:.6;margin-left:4px}
.act{margin-left:auto;border:0;background:none;color:var(--accent);font:500 13px "IBM Plex Mono",monospace;cursor:pointer;padding:5px 4px}
.act:hover{text-decoration:underline}
.day h2{cursor:pointer;user-select:none;display:flex;justify-content:space-between;gap:12px}
.day h2:hover{color:var(--ink)}
.day h2 .ok{display:inline-block;width:1em;transition:transform .15s}
.day.kapali h2 .ok{transform:rotate(-90deg)}
.day.kapali .item{display:none}
@media (max-width:600px){.filters,.row{padding-left:16px;padding-right:16px}main{padding:0 16px 48px}.act{margin-left:0}}
</style></head>
<body>
<header><div class="wrap"><h1>Haber Radarı</h1>
<div class="stamp">son tarama: __UPDATED__ · haftalık otomatik tarama</div></div></header>
<div class="wrap">
<nav class="filters row" id="filters"></nav>
<nav class="row" id="tarihler"></nav>
<main id="list"></main></div>
<script>
const ITEMS=__ITEMS_JSON__;
const LABELS=__LABELS_JSON__;
const ANAHTAR="haber-radar-kapali";
let cat="hepsi", tarih="hepsi";
let kapali=new Set();
try{kapali=new Set(JSON.parse(localStorage.getItem(ANAHTAR)||"[]"))}catch(e){}
function kaydet(){try{localStorage.setItem(ANAHTAR,JSON.stringify([...kapali]))}catch(e){}}
const TARIHLER=[...new Set(ITEMS.map(i=>i.first_seen||""))].sort().reverse();
function chip(txt,on,fn,n){const b=document.createElement("button");b.className="chip"+(on?" on":"");
  b.innerHTML=txt+(n!=null?`<span class="n">${n}</span>`:"");b.onclick=fn;return b}
function render(){
  const f=document.getElementById("filters");f.innerHTML='<span class="lbl">Konu</span>';
  ["hepsi",...new Set(ITEMS.map(i=>i.category))].forEach(c=>
    f.appendChild(chip(c==="hepsi"?"Tümü":(LABELS[c]||c),cat===c,()=>{cat=c;render()})));
  const t=document.getElementById("tarihler");t.innerHTML='<span class="lbl">Tarih</span>';
  const say=d=>ITEMS.filter(i=>(cat==="hepsi"||i.category===cat)&&i.first_seen===d).length;
  t.appendChild(chip("Tüm tarihler",tarih==="hepsi",()=>{tarih="hepsi";render()}));
  TARIHLER.forEach(d=>t.appendChild(chip(d,tarih===d,()=>{tarih=d;render()},say(d))));
  const herbiri=TARIHLER.slice(1);
  const hepsiKapali=herbiri.length&&herbiri.every(d=>kapali.has(d));
  const btn=document.createElement("button");btn.className="act";
  btn.textContent=hepsiKapali?"Hepsini aç":"Eskileri kapat";
  btn.onclick=()=>{if(hepsiKapali)kapali.clear();else{kapali=new Set(herbiri)}kaydet();render()};
  if(herbiri.length&&tarih==="hepsi")t.appendChild(btn);

  let items=ITEMS.filter(i=>(cat==="hepsi"||i.category===cat)&&(tarih==="hepsi"||i.first_seen===tarih));
  items=[...items].sort((a,b)=>(b.first_seen||"").localeCompare(a.first_seen||"")||(b.relevance||0)-(a.relevance||0));
  const list=document.getElementById("list");list.innerHTML="";
  if(!items.length){list.innerHTML='<p class="empty">Bu seçimde haber yok.</p>';return}
  let cur=null,sec=null;
  items.forEach(i=>{
    if(i.first_seen!==cur){cur=i.first_seen;const d=cur;
      sec=document.createElement("section");sec.className="day"+(kapali.has(d)&&tarih==="hepsi"?" kapali":"");
      const h=document.createElement("h2");
      h.innerHTML=`<span><span class="ok">▾</span> ${d} taraması</span><span>${items.filter(x=>x.first_seen===d).length} haber</span>`;
      h.onclick=()=>{kapali.has(d)?kapali.delete(d):kapali.add(d);kaydet();render()};
      sec.appendChild(h);list.appendChild(sec);}
    const a=document.createElement("article");a.className="item";
    const rel=i.relevance!=null?`<span class="rel">önem ${i.relevance}/10</span>`:"";
    a.innerHTML=`<h3><a href="${i.url}" target="_blank" rel="noopener">${i.title}</a></h3>
      <div class="meta"><span>${LABELS[i.category]||i.category}</span><span>${i.site||i.source}</span>${rel}</div>`;
    sec.appendChild(a);});
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

    # kopya kontrolü için son 7 günde bültene girmiş başlıklar
    yeni_id = {i["id"] for i in all_new}
    sinir = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    onceki = [i["title"] for i in sorted(existing.values(), key=lambda x: x.get("first_seen") or "")
              if i["id"] not in yeni_id and (i.get("first_seen") or "") >= sinir
              and (i.get("relevance") is None or i["relevance"] >= core.THRESHOLD)]
    filtered = core.llm_filter(all_new, onceki)
    from .ozet import ozetle, bulten_sayfasi
    filtered = ozetle(filtered)
    # eşiği geçemeyenler depodan da düşsün ki dashboard temiz kalsın
    dropped = {i["id"] for i in all_new} - {i["id"] for i in filtered}
    for did in dropped:
        existing.pop(did, None)
    core.save(existing)

        # Bülten yalnızca bu koşunun yenilerinden değil, haftanın TÜM geçen
    # haberlerinden kurulur. Aynı hafta ikinci kez çalışınca (elle tetikleme,
    # tekrar deneme) önceki koşunun haberleri artık silinmez, üstüne eklenir.
    hafta = dt.date.today().isocalendar()[:2]
    def _bu_hafta(i: dict) -> bool:
        try:
            return dt.date.fromisoformat(i.get("first_seen") or "").isocalendar()[:2] == hafta
        except ValueError:
            return False
    haftalik = [i for i in existing.values() if _bu_hafta(i)
                and (i.get("relevance") is None or i["relevance"] >= core.THRESHOLD)]
    print(f"Bu koşuda {len(filtered)} yeni haber geçti, haftalık toplam {len(haftalik)}")

    path, body = core.write_bulletin(haftalik)
    write_dashboard(existing)
    b = bulten_sayfasi(haftalik)
    print(f"Bülten sayfası: {b}")
    if filtered:
        yr, wk = hafta
        core.send_email(f"Haber Radarı — {yr}/{wk}. hafta ({len(haftalik)} haber)", body)
    print(f"\n{len(haftalik)} haber bültende → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
