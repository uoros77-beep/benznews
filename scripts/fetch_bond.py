# Daily bond discount rate -> data/bond.json (keeps old values on any failure)
import json, os, re, datetime, pathlib, urllib.request
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "bond.json"
LOG = ROOT / "data" / "bond_log.json"
URL = os.environ.get("BOND_URL", "")
KST = datetime.timezone(datetime.timedelta(hours=9))
LOCAL = ["goyang", "paju", "gimpo", "incheon"]
PAT = re.compile(r"서울\s*([0-9.]+)\s*%\s*[,·]\s*지방\s*([0-9.]+)\s*%\s*\(?\s*(\d{4}-\d{2}-\d{2})?")

def log(e):
    h = []
    try: h = json.loads(LOG.read_text(encoding="utf-8"))
    except Exception: pass
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(([e] + h)[:60], ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    now = datetime.datetime.now(KST).isoformat(timespec="seconds")
    if not URL: return log({"at": now, "ok": False, "why": "no BOND_URL"})
    try:
        raw = urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()
    except Exception as e: return log({"at": now, "ok": False, "why": "fetch: %s" % e})
    html = None
    for enc in ("utf-8", "cp949"):
        try: html = raw.decode(enc); break
        except UnicodeDecodeError: pass
    html = html or raw.decode("utf-8", "ignore")
    text = re.sub(r"&nbsp;|\s+", " ", re.sub(r"<[^>]+>", " ", html))
    m = PAT.search(text)
    if not m: return log({"at": now, "ok": False, "why": "text not found", "len": len(text)})
    s, l, d = float(m.group(1)), float(m.group(2)), m.group(3)
    if not (3 <= s <= 30 and 3 <= l <= 30): return log({"at": now, "ok": False, "why": "range %s %s" % (s, l)})
    cur = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    r = dict(cur.get("rates", {})); r["seoul"] = s
    for k in LOCAL: r[k] = l
    OUT.write_text(json.dumps({"updatedAt": (d + "T09:00:00+09:00") if d else now,
        "source": "채권할인율 서울 %s%%, 지방 %s%% (%s) auto" % (s, l, d or now[:10]),
        "rates": r}, ensure_ascii=False, indent=2), encoding="utf-8")
    log({"at": now, "ok": True, "seoul": s, "local": l, "day": d})

main()
