# Bond rate via headless browser (reads all frames). Keeps old values on failure, saves debug info.
import json, os, re, datetime, pathlib
from playwright.sync_api import sync_playwright
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT, LOG, DBG = ROOT/"data"/"bond.json", ROOT/"data"/"bond_log.json", ROOT/"data"/"debug.json"
URL = os.environ.get("BOND_URL") or "http://www.cartok.com/"
KST = datetime.timezone(datetime.timedelta(hours=9))
LOCAL = ["goyang", "paju", "gimpo", "incheon"]
PAT = re.compile(r"서울\s*([0-9.]+)\s*%\s*[,·]\s*지방\s*([0-9.]+)\s*%\s*\(?\s*(\d{4}-\d{2}-\d{2})?")
now = datetime.datetime.now(KST).isoformat(timespec="seconds")

def log(e):
    h = []
    try: h = json.loads(LOG.read_text(encoding="utf-8"))
    except Exception: pass
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(([e] + h)[:60], ensure_ascii=False, indent=2), encoding="utf-8")

def texts(page):
    out = []
    for f in page.frames:
        try: out.append((f.url, f.evaluate("document.body ? document.body.innerText : ''")))
        except Exception as e: out.append((f.url, "ERR %s" % e))
    return out

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(locale="ko-KR")
    dbg = {"at": now, "pages": []}
    found = None
    try:
        pg.goto(URL, timeout=60000, wait_until="networkidle")
        pg.wait_for_timeout(3000)
        for u, t in texts(pg):
            dbg["pages"].append({"url": u, "len": len(t), "head": t[:1500]})
            m = PAT.search(re.sub(r"\s+", " ", t))
            if m and not found: found = m
        if not found:
            links = []
            for f in pg.frames:
                try: links += f.evaluate("[...document.querySelectorAll('a')].map(a=>[a.innerText.trim().slice(0,30),a.href]).filter(x=>/등록|계산|취득|채권|공채/.test(x[0]+x[1]))")
                except Exception: pass
            dbg["links"] = links[:40]
            for name, href in links[:6]:
                try:
                    pg.goto(href, timeout=45000, wait_until="networkidle"); pg.wait_for_timeout(2500)
                    for u, t in texts(pg):
                        dbg["pages"].append({"url": u, "len": len(t), "head": t[:1500]})
                        m = PAT.search(re.sub(r"\s+", " ", t))
                        if m: found = m; dbg["hit"] = u; break
                except Exception as e: dbg["pages"].append({"url": href, "err": str(e)[:200]})
                if found: break
    except Exception as e: dbg["err"] = str(e)[:300]
    b.close()
DBG.write_text(json.dumps(dbg, ensure_ascii=False, indent=1), encoding="utf-8")
if not found:
    log({"at": now, "ok": False, "why": "text not found (browser)"})
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
