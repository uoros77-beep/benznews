"""벤츠 동향 사진 자동 저장 (GitHub Actions 에서 실행).
data/news.json 각 소식의 원문 기사에서 대표 사진을 찾아 고화질(가로 최대 1600px) JPEG 로
news-img/<id>.jpg 에 저장하고, photos 를 저장된 사진 주소로 바꿉니다.
- photos 첫 사진이 외부 https 주소이면 그 사진을 먼저 받습니다(공식 보도 사진 지정용).
- 없으면 원문 기사의 대표 사진(og:image 등)과 본문 큰 사진 중 가로 1000px 이상을 고릅니다.
- 세 번 실패한 소식은 다시 시도하지 않습니다(data/news_photo_miss.json).
- 소식에서 빠진 사진 파일은 지웁니다.
사용: python scripts/news_photos.py   (테스트: NEWS_IMG_BASE, NEWS_TODAY 환경변수)"""
import io, json, os, sys, urllib.parse
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
NEWS = os.path.join(ROOT, 'data', 'news.json')
MISS = os.path.join(ROOT, 'data', 'news_photo_miss.json')
DIR = os.path.join(ROOT, 'news-img')
BASE = os.environ.get('NEWS_IMG_BASE', 'https://raw.githubusercontent.com/uoros77-beep/benznews/main/news-img/')
MAXW, HQ, LOW = 1600, 1000, 760
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

FIND = """(minw) => {
  const out = [];
  const sel = ['meta[property="og:image:secure_url"]', 'meta[property="og:image"]', 'meta[name="og:image"]',
               'meta[name="twitter:image"]', 'meta[name="twitter:image:src"]', 'meta[property="twitter:image"]',
               'link[rel="image_src"]'];
  for (const s of sel) { const e = document.querySelector(s); const v = e && (e.content || e.href); if (v) out.push(v); }
  for (const sc of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const walk = (o) => { if (!o || typeof o !== 'object') return;
      if (Array.isArray(o)) return o.forEach(walk);
      const im = o.image; if (typeof im === 'string') out.push(im);
      else if (Array.isArray(im)) im.forEach(x => out.push(typeof x === 'string' ? x : x && x.url));
      else if (im && im.url) out.push(im.url);
      if (o['@graph']) walk(o['@graph']); }; walk(JSON.parse(sc.textContent)); } catch (e) {}
  }
  const big = [...document.images].map(i => ({u: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight}))
    .filter(o => o.u && o.w >= minw && o.h > 0 && o.w / o.h >= 1.15 && o.w / o.h <= 2.6)
    .sort((a, b) => b.w * b.h - a.w * a.h);
  big.slice(0, 6).forEach(o => out.push(o.u));
  return out.filter(Boolean);
}"""


def web(u):
    u = str(u or '')
    return u.startswith('https://') or (bool(os.environ.get('NEWS_TEST')) and u.startswith('http://'))


def load(p, d):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return d


def hosted(ph, iid):
    return isinstance(ph, dict) and str(ph.get('src', '')).startswith(BASE) and \
        os.path.exists(os.path.join(DIR, iid + '.jpg'))


def to_rgb(im):
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[3])
        return bg
    return im.convert('RGB')


def grab(req, url, ref):
    try:
        r = req.get(url, headers={'Referer': ref or url, 'Accept': 'image/avif,image/webp,image/*,*/*;q=0.8'},
                    timeout=30000, max_redirects=5)
        if not r.ok:
            return None
        b = r.body()
        if len(b) < 15000:
            return None
        im = Image.open(io.BytesIO(b))
        im.load()
        w, h = im.size
        if h <= 0 or not 1.15 <= w / h <= 2.6:
            return None
        return to_rgb(im)
    except Exception as e:
        print('  사진 받기 실패', url[:90], type(e).__name__)
        return None


def candidates(page, src_url):
    try:
        page.goto(src_url, timeout=45000, wait_until='domcontentloaded')
        try:
            page.wait_for_load_state('networkidle', timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        out = page.evaluate(FIND, LOW)
        return [urllib.parse.urljoin(page.url, u) for u in out]
    except Exception as e:
        print('  원문 열기 실패', src_url[:90], type(e).__name__)
        return []


def save(im, iid):
    w, h = im.size
    if w > MAXW:
        im = im.resize((MAXW, round(h * MAXW / w)), Image.LANCZOS)
    os.makedirs(DIR, exist_ok=True)
    im.save(os.path.join(DIR, iid + '.jpg'), 'JPEG', quality=86, optimize=True, progressive=True)
    return im.size


def main():
    d = load(NEWS, None)
    if not d or not isinstance(d.get('items'), list):
        print('news.json 을 읽지 못했습니다'); return 1
    miss = load(MISS, {})
    todo = []
    for it in d['items']:
        iid = str(it.get('id', ''))
        phs = [p for p in (it.get('photos') or []) if isinstance(p, dict)]
        if not iid or (phs and hosted(phs[0], iid)):
            continue
        ext = phs[0]['src'] if phs and web(phs[0].get('src')) else None
        if not ext and miss.get(iid, 0) >= 3:
            continue
        todo.append((it, phs, ext))
    changed = False
    if todo:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(user_agent=UA, locale='ko-KR', viewport={'width': 1440, 'height': 900},
                                device_scale_factor=2)
            page = ctx.new_page()
            for it, phs, ext in todo:
                iid, src = it['id'], (it.get('src') or {})
                print('소식', iid)
                pick = None
                if ext:
                    pick = grab(ctx.request, ext, src.get('url'))
                if pick is None and web(src.get('url')):
                    seen, best = set(), None
                    for u in candidates(page, src['url']):
                        if u in seen or not u.startswith('http'):
                            continue
                        seen.add(u)
                        im = grab(ctx.request, u, src['url'])
                        if im is None:
                            continue
                        if im.size[0] >= HQ:
                            pick = im; break
                        if im.size[0] >= LOW and (best is None or im.size[0] > best.size[0]):
                            best = im
                    pick = pick or best
                rest = [q for q in phs if not str(q.get('src', '')).startswith(('https://', 'http://'))]
                if pick is None:
                    miss[iid] = miss.get(iid, 0) + 1
                    if ext:
                        it['photos'] = rest; changed = True
                    print('  사진 없음 (시도 %d회)' % miss[iid])
                    continue
                w, h = save(pick, iid)
                alt = (phs[0].get('alt') if phs else '') or it.get('title', '')
                it['photos'] = [{'src': BASE + iid + '.jpg', 'alt': str(alt)[:60], 'credit': str(src.get('name', ''))[:40],
                                 'w': w, 'h': h}] + rest
                miss.pop(iid, None)
                changed = True
                print('  저장', w, 'x', h)
            b.close()
    keep = {str(it.get('id')) + '.jpg' for it in d['items']}
    if os.path.isdir(DIR):
        for f in os.listdir(DIR):
            if f.endswith('.jpg') and f not in keep:
                os.remove(os.path.join(DIR, f)); print('지움', f)
    ids = {str(it.get('id')) for it in d['items']}
    miss = {k: v for k, v in miss.items() if k in ids}
    if changed:
        with open(NEWS, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2); f.write('\n')
    with open(MISS, 'w', encoding='utf-8') as f:
        json.dump(miss, f, ensure_ascii=False, indent=2); f.write('\n')
    print('끝: 처리 %d건' % len(todo))
    return 0


if __name__ == '__main__':
    sys.exit(main())
