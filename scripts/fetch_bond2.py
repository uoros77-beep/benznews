# Bond rate via headless browser: opens cartok, clicks the calculator menus, reads all frames/popups.
import json, os, re, datetime, pathlib
from playwright.sync_api import sync_playwright
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT, LOG, DBG = ROOT/"data"/"bond.json", ROOT/"data"/"bond_log.json", ROOT/"data"/"debug.json"
URL = os.environ.get("BOND_URL") or "http://www.cartok.com/"
KST = datetime.timezone(datetime.timedelta(hours=9))
LOCAL = ["goyang", "paju", "gimpo", "incheon"]
PAT = re.compile(r"서울\s*([0-9.]+)\s*%\s*[,·]\s*지방\s*([0-9.]+)\s*%\s*\(?\s*(\d{4}-\d{2}-\d{2})?")
MENUS = ["등록비용 계산기", "채권 시세", "채권(공채) 매입"]
now = datetime.datetime.now(KST).isoformat(timespec="seconds")
dbg = {"at": now, "pages": []}

def log(e):
    h = []
    try: h = json.loads(LOG.read_text(encoding="utf-8"))
    except Exception: pass
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(([e] + h)[:60], ensure_ascii=False, indent=2), encoding="utf-8")

def scan(ctx, tag):
    for pg in ctx.pages:
        for f in pg.frames:
            try: t = f.evaluate("document.body ? document.body.innerText : ''")
            except Exception as e: t = "ERR %s" % e
            dbg["pages"].append({"tag": tag, "url": f.url, "len": len(t), "head": t[:800]})
            m = PAT.search(re.sub(r"\s+", " ", t))
            if m: dbg["hit"] = f.url; return m
    return None

found = None
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(locale="ko-KR")
    pg = ctx.new_page()
    try:
        pg.goto(URL, timeout=60000, wait_until="networkidle"); pg.wait_for_timeout(2500)
        found = scan(ctx, "home")
        for name in MENUS:
            if found: break
            for f in pg.frames:
                try:
                    el = f.get_by_text(name, exact=False).first
                    if el.count() == 0: continue
                    dbg.setdefault("menu", []).append({"name": name, "html": el.evaluate("e=>(e.closest('a,li,div,td')||e).outerHTML.slice(0,400)")})
                    el.click(timeout=8000); pg.wait_for_timeout(4000)
                    for q in ctx.pages:
                        try: q.wait_for_load_state("networkidle", timeout=15000)
                        except Exception: pass
                    found = scan(ctx, name)
                    break
                except Exception as e: dbg.setdefault("clickerr", []).append("%s: %s" % (name, str(e)[:150]))
            if not found:
                try: pg.goto(URL, timeout=60000, wait_until="networkidle"); pg.wait_for_timeout(1500)
                except Exception: pass
    except Exception as e: dbg["err"] = str(e)[:300]
    b.close()
DBG.write_text(json.dumps(dbg, ensure_ascii=False, indent=1), encoding="utf-8")
if not found:
    log({"at": now, "ok": False, "why": "text not found (browser+click)"})
else:
    s, l, d = float(found.group(1)), float(found.group(2)), found.group(3)
    if not (3 <= s <= 30 and 3 <= l <= 30):
        log({"at": now, "ok": False, "why": "range %s %s" % (s, l)})
    else:
        cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        r = dict(cur.get("rates", {})); r["seoul"] = s
        for k in LOCAL: r[k] = l
        OUT.write_text(json.dumps({"updatedAt": (d + "T09:00:00+09:00") if d else now,
            "source": "채권할인율 서울 %s%%, 지방 %s%% (%s) auto" % (s, l, d or now[:10]),
            "rates": r}, ensure_ascii=False, indent=2), encoding="utf-8")
        log({"at": now, "ok": True, "seoul": s, "local": l, "day": d})
