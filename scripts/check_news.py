"""벤츠 동향(data/news.json) 검사. 문제가 있으면 이유를 출력하고 종료 코드 1.
사용: python3 scripts/check_news.py [data/news.json]"""
import json, re, sys, datetime, os
base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base, 'news.json')
photos = set(json.load(open(os.path.join(base, 'news_photos.json'), encoding='utf-8')))
pages = set(json.load(open(os.path.join(base, 'news_pages.json'), encoding='utf-8')))
CATS = {"국내", "신차", "기술", "브랜드"}
KR = {"국내 판매 중", "국내 출시 확정", "국내 출시 미정", "해당 없음"}
err = []
def bad(i, m): err.append(f"[{i}] {m}")
def isdate(s):
    try: return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', s)) and datetime.date.fromisoformat(s)
    except Exception: return False
def text_ok(i, s, lo, hi, what):
    if not isinstance(s, str): return bad(i, f"{what}: 글자가 아님")
    if not lo <= len(s) <= hi: bad(i, f"{what}: 길이 {len(s)} (허용 {lo}~{hi})")
    if '—' in s or '–' in s: bad(i, f"{what}: 긴 줄표(—) 사용 금지")
    if re.search(r'[<>]', s): bad(i, f"{what}: < > 기호 금지")
    if re.search(r'전기\s?(CLA|GLC|GLB|GLA|VLE|C-Class|C클래스|G-Class|G클래스|CLE|E-Class)', s): bad(i, f"{what}: 'Electric ○○' 표기 사용")
try:
    d = json.load(open(path, encoding='utf-8'))
except Exception as e:
    print("JSON 읽기 실패:", e); sys.exit(1)
up = d.get('updated')
if not isdate(up): err.append("updated 날짜 형식 오류")
items = d.get('items')
if not isinstance(items, list) or not 1 <= len(items) <= 60: err.append("items 는 1~60건이어야 함")
items = items or []
ids = set()
for n, it in enumerate(items):
    i = it.get('id', f'#{n}')
    if not re.fullmatch(r'[a-z0-9-]{6,80}', str(it.get('id', ''))): bad(i, "id 형식(영소문자·숫자·-)")
    if i in ids: bad(i, "id 중복")
    ids.add(i)
    if not isdate(it.get('date', '')): bad(i, "date 형식")
    elif isdate(up) and it['date'] > up: bad(i, "date 가 updated 보다 미래")
    if it.get('cat') not in CATS: bad(i, f"cat 은 {sorted(CATS)} 중 하나")
    if it.get('kr') not in KR: bad(i, f"kr 은 {sorted(KR)} 중 하나")
    text_ok(i, it.get('title'), 8, 60, "title")
    pts = it.get('points')
    if not isinstance(pts, list) or not 2 <= len(pts) <= 4: bad(i, "points 는 2~4줄")
    else:
        for p in pts: text_ok(i, p, 15, 170, "points")
    if it.get('note'): text_ok(i, it['note'], 8, 120, "note")
    for ph in it.get('photos', []):
        if ph.get('src') not in photos: bad(i, f"photos: 허용 목록에 없는 사진 {ph.get('src')}")
        text_ok(i, ph.get('alt', ''), 2, 40, "photos.alt")
    for l in it.get('links', []):
        if l.get('href') not in pages: bad(i, f"links: 사이트에 없는 페이지 {l.get('href')}")
        text_ok(i, l.get('label', ''), 2, 30, "links.label")
    s = it.get('src') or {}
    if not str(s.get('url', '')).startswith('https://'): bad(i, "src.url 은 https 원문 주소")
    text_ok(i, s.get('name', ''), 2, 40, "src.name")
dates = [it.get('date', '') for it in items]
if dates != sorted(dates, reverse=True): err.append("items 는 최신 날짜가 먼저 오도록 정렬")
if err:
    print("문제 %d건" % len(err)); print("\n".join(err)); sys.exit(1)
print("통과: %d건, 최신 %s" % (len(items), dates[0] if dates else '-'))
