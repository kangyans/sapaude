#!/usr/bin/env python3
"""Import kangyan.bearblog.dev into this static site.

Downloads the Bear pages (home, 博文, 閒話, 資料庫, 影冊, 遊戲, every post and
every internal page they link to), then rewrites them into the site's own
layout under site/, keeping Bear's URLs.

Usage (from anywhere):
    python3 tools/import_bear.py            # fetch fresh copies, then build
    python3 tools/import_bear.py --offline  # rebuild from the cached download

Downloads are cached in .bear-cache/ (git-ignored). Only the standard library
is used. Images in the pages are downloaded once into site/assets/images/ (named by
a hash of their URL, so re-runs skip them) and the pages point at the local
copies; with --offline, images not yet downloaded keep their remote URL.
The 聯繫 link is taken from the nav of the downloaded Bear home page.
"""
import argparse
import glob
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import OrderedDict

BASE = 'https://kangyan.bearblog.dev'
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, 'site')          # what Cloudflare Pages serves (build output directory)
CACHE = os.path.join(REPO, '.bear-cache')
IMAGES = os.path.join(SITE, 'assets', 'images')
UA = 'Mozilla/5.0 (static-site importer)'  # Bear pages
IMG_UA = 'sapaude-site-importer/1.0 (python-urllib)'  # image hosts; Wikimedia rejects browser-like UAs

# Section pages: Bear path -> nav label
# Bear pages left out of this site on purpose: not built, and every link to
# them (archive entries, series index lines, prev/next links) is removed.
EXCLUDE = {
    '/eatstory/00/',   # 食林廣記 · 零 (cover page)
    '/poems/cover/',   # 人間詞話 · 零 (cover page)
}

SECTIONS = OrderedDict([('/blog/', '博文'), ('/twix/', '閒話'), ('/movies/', '影冊'),
                        ('/games/', '遊戲'), ('/arxiv/', '資料庫')])


# ---------------------------------------------------------------- fetching

def cache_file(path):
    name = path.strip('/').replace('/', '__') or 'home'
    return os.path.join(CACHE, name + '.html')


def fetch(path, delay=1.5, tries=5):
    """Download one Bear page into the cache, backing off on HTTP 429."""
    for attempt in range(tries):
        req = urllib.request.Request(BASE + path, headers={'User-Agent': UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            with open(cache_file(path), 'wb') as f:
                f.write(data)
            time.sleep(delay)
            return 200
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                wait = 20 * (attempt + 1)
                print(f'  429 on {path}, waiting {wait}s', flush=True)
                time.sleep(wait)
                continue
            return e.code
    return 429


def norm(path):
    path = path.split('#')[0].split('?')[0]
    if not path.endswith('/'):
        path += '/'
    return path.lower()


def internal_links(fragment):
    out = []
    for h in re.findall(r'href=[\'"]([^\'"]+)[\'"]', fragment):
        if h.startswith(BASE):
            h = h[len(BASE):] or '/'
        if h.startswith('/') and not h.startswith('//') and '?' not in h:
            out.append(norm(h))
    return out


def blog_entries(blog_doc):
    """(datetime, path, title) for every post in Bear's /blog/ list."""
    return [(dt, norm(href), t.strip()) for dt, href, t in re.findall(
        r'<li data-tags="[^"]*">.*?datetime="([^"]+)".*?<a href="([^"]+)">(.*?)</a>', blog_doc, re.S)]


def crawl():
    os.makedirs(CACHE, exist_ok=True)
    for p in ['/'] + list(SECTIONS):
        code = fetch(p)
        print(f'{code} {p}', flush=True)
        if code != 200:
            sys.exit(f'could not fetch {p} (HTTP {code})')
    pages = [p for _, p, _ in blog_entries(read(cache_file('/blog/')))]
    for p in ['/'] + list(SECTIONS):
        pages += internal_links(main_of(read(cache_file(p))))
    skip = {'/'} | set(SECTIONS)
    todo = []
    for p in pages:
        if p not in skip and p not in todo:
            todo.append(p)
    status = {}
    for p in todo:
        status[p] = fetch(p)
        print(f'{status[p]} {p}', flush=True)
    with open(os.path.join(CACHE, 'fetched.json'), 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    return status



# ---------------------------------------------------------------- images

IMAGE_EXT = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp', 'image/gif': '.gif',
             'image/svg+xml': '.svg', 'image/avif': '.avif'}


class ImageStore:
    """Downloads remote <img> sources into assets/images/ and rewrites src."""

    def __init__(self, online):
        self.online = online
        self.done = {}      # url -> local path or None (failed)
        self.failed = []
        os.makedirs(IMAGES, exist_ok=True)

    def local(self, url):
        if url in self.done:
            return self.done[url]
        key = hashlib.sha1(html.unescape(url).encode()).hexdigest()[:16]
        found = glob.glob(os.path.join(IMAGES, key + '.*'))
        path = None
        if found:
            path = '/assets/images/' + os.path.basename(found[0])
        elif self.online:
            path = self._download(html.unescape(url), key)
        self.done[url] = path
        return path

    def _download(self, url, key):
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': IMG_UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    ctype = r.headers.get_content_type()
                    data = r.read()
                ext = IMAGE_EXT.get(ctype)
                if not ext:
                    self.failed.append((url, ctype))
                    return None
                name = key + ext
                with open(os.path.join(IMAGES, name), 'wb') as f:
                    f.write(data)
                print(f'  image {len(data) // 1024:>5} KB  {url[:80]}', flush=True)
                time.sleep(0.3)
                return '/assets/images/' + name
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(15 * (attempt + 1))
                    continue
                self.failed.append((url, e.code))
                return None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < 2:
                    time.sleep(5)
                    continue
                self.failed.append((url, str(e)))
                return None

    def rewrite(self, doc):
        def rep(m):
            before, q, url = m.group(1), m.group(2), m.group(3)
            new = self.local(url)
            return f'<img{before}src={q}{new}{q}' if new else m.group(0)
        return re.sub(r'<img([^>]*?\s)src=([\'"])(https?://[^\'"]+)\2', rep, doc)

# ---------------------------------------------------------------- converting

def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def main_of(doc):
    m = re.search(r'<main>(.*?)</main>', doc, re.S)
    return m.group(1) if m else ''


def title_of(doc):
    t = re.search(r'<title>(.*?)</title>', doc, re.S).group(1).strip()
    return html.unescape(re.sub(r'\s*[–|-]\s*Sapere Aude$', '', t))


def contact_href(home_doc):
    """The 聯繫 link exactly as Bear's nav has it."""
    nav = re.search(r'<nav>(.*?)</nav>', home_doc, re.S)
    m = re.search(r'href=[\'"]([^\'"]+)[\'"]>\s*聯繫', nav.group(1) if nav else '')
    return m.group(1) if m else BASE + '/'


def make_link_fixer(local):
    def rep(m):
        q, url = m.group(1), m.group(2)
        u = (url[len(BASE):] or '/') if url.startswith(BASE) else url
        if u.startswith('/') and not u.startswith('//'):
            path, _, frag = u.partition('#')
            if '?' not in path and norm(path) in local:
                new = norm(path) + ('#' + frag if frag else '')
            else:
                new = BASE + u  # Bear-only URLs (search, feed, unpublished) stay on Bear
            return f'href={q}{new}{q}'
        return m.group(0)
    return lambda s: re.sub(r'\bhref=([\'"])([^\'"]*)\1', rep, s)


def drop_excluded_links(s):
    """Remove <a> elements pointing at EXCLUDE pages, with a trailing <br>."""
    def rep(m):
        url = m.group(2)
        if url.startswith(BASE):
            url = url[len(BASE):] or '/'
        return '' if url.startswith('/') and norm(url) in EXCLUDE else m.group(0)
    return re.sub(r'<a\b[^>]*\bhref=([\'"])([^\'"]*)\1[^>]*>.*?</a>(?:\s*<br\s*/?>)?', rep, s, flags=re.S)


def clean(s, fix_links):
    s = re.sub(r'<script.*?</script>', '', s, flags=re.S)
    s = re.sub(r'<form id="upvote-form".*?</form>', '', s, flags=re.S)
    s = re.sub(r'</?(?:body|html)\b[^>]*>', '', s)
    s = re.sub(r'<a rel="nofollow" href="/blog/\?q=[^"]*">(#[^<]*)</a>', r'<span class="tag">\1</span>', s)
    s = drop_excluded_links(s)   # before fix_links, which would make them absolute Bear URLs
    s = fix_links(s)
    s = re.sub(r'\n\s*\n\s*\n+', '\n\n', s)
    return s.strip()


def post_body(m):
    """Replace Bear's <h1> + <p><i><time> header with the site's post header."""
    hm = re.match(r'\s*<h1>(.*?)</h1>\s*<p>\s*<i>\s*<time datetime="([^"]+)">.*?</time>\s*</i>\s*</p>', m, re.S)
    if not hm:
        return None, m
    title, dt = hm.group(1).strip(), hm.group(2)
    head = (f'<header class="post-header">\n<h1 class="post-heading">{title}</h1>\n'
            f'<time datetime="{dt}">{dt[:10].replace("-", "/")}</time>\n</header>')
    return title, head + '\n<div class="post-body">\n' + m[hm.end():].strip() + '\n</div>'


def page(nav_items, path, title, body, script=''):
    cur = ' aria-current="page"'
    nav = ''.join(f'<li><a href="{h}"{cur if h == path else ""}>{n}</a></li>' for h, n in nav_items)
    t = 'Sapere Aude' + (f' · {html.escape(title)}' if title else '')
    return f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title>
<link rel="stylesheet" href="/assets/style.css">
<link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20100%20100'%3E%3Ctext%20y='.9em'%20font-size='90'%3E👨🏻‍🚀%3C/text%3E%3C/svg%3E">
</head>
<body>
<header class="site-header">
  <a class="site-title" href="/"><h1>Sapere Aude</h1></a>
  <p class="site-tagline">敢於求知</p>
  <nav class="site-nav" aria-label="主選單">
    <ul>{nav}</ul>
  </nav>
</header>
<main>
{body}
</main>
<footer class="site-footer">
  <p>Sapere Aude</p>
</footer>
{script}</body>
</html>
'''


def write(path, doc):
    out = os.path.join(SITE, path.strip('/'), 'index.html')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(doc)


def archive(groups):
    out = ['<section class="archive">']
    for y, items in groups.items():
        out.append(f'<h3 class="year">{y}</h3>\n<ul class="blog-posts">')
        for d, href, name in items:
            out.append(f'<li><time>{d.replace("-", "/")}</time><a class="post-title" href="{href}">{name}</a></li>')
        out.append('</ul>')
    out.append('</section>')
    return '\n'.join(out)


CALENDAR = '''<div class="calendar-card" aria-label="今日">
  <div class="calendar-top">
    <span id="cal-ganzhi"></span>
    <span id="cal-year"></span>
  </div>
  <div class="calendar-content">
    <div class="calendar-left">
      <div class="calendar-month" id="cal-month"></div>
      <div class="calendar-day" id="cal-day"></div>
      <div class="calendar-week" id="cal-week"></div>
    </div>
    <div class="calendar-right">
      <div class="calendar-lunar" id="cal-poem1"></div>
      <div class="calendar-lunar" id="cal-poem2"></div>
    </div>
  </div>
  <div class="calendar-bottom">
    <span class="yi"><strong>宜</strong>讀書・行路・作文</span>
    <span class="seal" id="cal-zodiac"></span>
  </div>
</div>'''


def movie_rows(m):
    """影冊: regroup Bear's flat movie grid into Netflix-style rows.

    最近觀看 = the first 12 cards in Bear's order (most recent first); then
    rating rows, each sorted high to low. assets/rows.js adds the arrows."""
    cards = []
    for attrs, title, rating in re.findall(
            r'<div class="movie-card">\s*<img([^>]*)>\s*<div class="movie-title">(.*?)</div>'
            r'\s*<div class="movie-rating">(.*?)</div>', m, re.S):
        x = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', rating)
        cards.append({'img': attrs.strip(), 'title': title.strip(), 'rating': rating.strip(),
                      'score': float(x.group(1)) if x else None})
    if not cards:
        return m

    def card(c):
        return (f'<div class="movie-card"><img {c["img"]} loading="lazy">'
                f'<div class="movie-title">{c["title"]}</div>'
                f'<div class="movie-rating">{c["rating"]}</div></div>')

    scored = sorted((c for c in cards if c['score'] is not None), key=lambda c: -c['score'])
    rows = [('最近觀看', cards[:12]),
            ('九分以上', [c for c in scored if c['score'] >= 9]),
            ('八分', [c for c in scored if 8 <= c['score'] < 9]),
            ('七分及以下', [c for c in scored if c['score'] < 8])]
    out = [f'<p class="page-meta">共 {len(cards)} 部</p>']
    for name, items in rows:
        if not items:
            continue
        out.append(f'<section class="row">\n<h3 class="row-title">{name}<span class="row-count">{len(items)}</span></h3>\n'
                   '<div class="row-viewport">\n<div class="row-track">\n'
                   + '\n'.join(card(c) for c in items) + '\n</div>\n</div>\n</section>')
    return '\n'.join(out)


def game_rows(m):
    """遊戲: each Bear section (<h3> + game-grid) becomes a row, like 影冊."""
    def rep(x):
        head_id, head, cards = x.group(1), x.group(2).strip(), x.group(3)
        n = cards.count('class="game-card"')
        return (f'<section class="row row-games" id="{head_id}">\n'
                f'<h3 class="row-title">{head}<span class="row-count">{n}</span></h3>\n'
                '<div class="row-viewport">\n<div class="row-track">\n' + cards.strip()
                + '\n</div>\n</div>\n</section>\n')
    pat = r'<h3 id=["\']?([^"\' >]+)["\']?>(.*?)</h3>\s*<div class="game-grid">(.*?)</div>\s*(?=<hr>|</div>\s*$)'
    m = re.sub(pat, rep, m, flags=re.S)
    m = re.sub(r'\s*<hr>\s*', '\n', m)
    m = m.replace('<img ', '<img loading="lazy" ')
    return m


def directory(m):
    """資料庫: group each <h4> + <ul> into a directory block, and runs of blocks
    into a two-column grid, like a newspaper's listings page."""
    m = re.sub(r'<div class=["\']?custom-box["\']?>', '<div class="directory">', m, count=1)
    m = re.sub(r'(<h4\b[^>]*>.*?</h4>\s*<ul>.*?</ul>)', r'<div class="dir-group">\1</div>', m, flags=re.S)
    m = re.sub(r'((?:<div class="dir-group">.*?</ul></div>\s*)+)', r'<div class="dir-grid">\1</div>', m, flags=re.S)
    m = re.sub(r'(<h3 id=["\']?鳴謝["\']?>.*?)(?=</div>\s*$)', r'<div class="colophon">\1</div>', m, flags=re.S)
    m = re.sub(r'\s*<hr>\s*', '\n', m)
    return m


def twix_datelines(m):
    """閒話: turn each note's '公佈於 MM/DD/YYYY' into a dateline showing MM/DD (year kept in datetime)."""
    def rep(x):
        mo, d, y = x.group(1), x.group(2), x.group(3)
        return (f'<p class="twix-date"><time datetime="{y}-{mo}-{d}">'
                f'<span class="md">{mo}/{d}</span></time>')
    return re.sub(r'<p>\s*公佈於\s*(\d{2})/(\d{2})/(\d{4})\s*(?:</p>)?', lambda x: rep(x) + '</p>', m)


def build(status, images):
    ok = [p for p, c in status.items() if c == 200 and p not in EXCLUDE]
    local = set(ok) | {'/'} | set(SECTIONS)
    fix = make_link_fixer(local)
    home_doc = read(cache_file('/'))
    nav_items = list(SECTIONS.items()) + [(contact_href(home_doc), '聯繫')]

    def out(path, title, body, script=''):
        write(path, images.rewrite(page(nav_items, path, title, body, script)))

    for p in ok:
        doc = read(cache_file(p))
        m = clean(main_of(doc), fix)
        title, body = post_body(m)
        if title is None:
            title = title_of(doc)
            body = f'<h2 class="page-title">{title}</h2>\n<div class="post-body">\n{m}\n</div>'
        # vertical-text posts get the band-fitting script (see assets/vertical.js)
        has_vertical = re.search(r'class=["\']?[^"\'>]*\bvertical\b', body)  # quoted or bare class=vertical
        vscript = '<script src="/assets/vertical.js" defer></script>\n' if has_vertical else ''
        out(p, re.sub('<[^>]+>', '', title), body, vscript)

    groups = OrderedDict()
    entries = [e for e in blog_entries(read(cache_file('/blog/'))) if e[1] not in EXCLUDE]
    for dt, href, name in entries:
        groups.setdefault(dt[:4], []).append((dt[5:10], href, name))
    out('/blog/', '博文', f'<h2 class="page-title">博文</h2>\n<p class="page-meta">共 {len(entries)} 篇</p>\n'
        + archive(groups))

    for p, name in SECTIONS.items():
        if p == '/blog/':
            continue
        m = clean(main_of(read(cache_file(p))), fix)
        if p == '/movies/':
            m = movie_rows(m)
        if p == '/games/':
            m = game_rows(m)
        if p == '/arxiv/':
            m = directory(m)
        if p == '/twix/':
            m = twix_datelines(m)
            # drop the 說明 line about underlining names/places (no longer underlined)
            m = re.sub(r'<p[^>]*>\s*說明：人名、地名加.*?</p>\s*', '', m, count=1, flags=re.S)
        script = '<script src="/assets/rows.js" defer></script>\n' if p in ('/movies/', '/games/') else ''
        out(p, name, f'<h2 class="page-title">{name}</h2>\n{m}', script)

    hm = clean(main_of(home_doc), fix)
    # 專欄: rebuild Bear's series box as a grid of numbered tiles
    sm = re.search(r'<div class="series-list">(.*?)</div>', hm, re.S)
    series = ''
    if sm:
        tiles = []
        for i, (href, name) in enumerate(re.findall(r'<a href=[\'"]([^\'"]+)[\'"]>(.*?)</a>', sm.group(1), re.S)):
            name = re.sub(r'^\s*(?:<|&lt;|《|〈)|(?:>|&gt;|》|〉)\s*$', '', name.strip())
            no = '壹貳參肆伍陸柒捌玖拾'[i] if i < 10 else str(i + 1)
            tiles.append(f'<li><a href="{href}"><span class="series-no">{no}</span>'
                         f'<span class="series-name">{name}</span></a></li>')
        series = ('<nav class="series" aria-label="專欄">\n<h2 class="series-heading">專欄</h2>\n'
                  '<ul class="series-grid">\n' + '\n'.join(tiles) + '\n</ul>\n</nav>')
    hgroups = OrderedDict()
    for y, block in re.findall(r'<h4>(\d{4})</h4>\s*</p>\s*<p>(.*?)</p>', hm, re.S):
        for d, href, name in re.findall(r'(\d\d-\d\d)\s*<a href=[\'"]([^\'"]+)[\'"]>(.*?)</a>', block, re.S):
            hgroups.setdefault(y, []).append((d, href, name.strip()))
    out('/', '', f'<section class="home-top">\n{CALENDAR}\n{series}\n</section>\n' + archive(hgroups),
        '<script src="/assets/calendar.js"></script>\n')

    failed = {p: c for p, c in status.items() if c != 200}
    print(f'built {len(ok)} pages + home + {len(SECTIONS)} sections; '
          f'{len(entries)} posts in 博文; {sum(len(v) for v in hgroups.values())} on home')
    if failed:
        print('not fetched (left linking to Bear):', failed)
    n_local = sum(1 for v in images.done.values() if v)
    print(f'images: {n_local}/{len(images.done)} local')
    for url, why in images.failed:
        print(f'  image not downloaded ({why}): {url}')


def main():
    ap = argparse.ArgumentParser(description='Import kangyan.bearblog.dev into this static site.')
    ap.add_argument('--offline', action='store_true', help='rebuild from .bear-cache/ without downloading')
    args = ap.parse_args()
    if args.offline:
        with open(os.path.join(CACHE, 'fetched.json'), encoding='utf-8') as f:
            status = {k: int(v) for k, v in json.load(f).items()}
    else:
        status = crawl()
    build(status, ImageStore(online=not args.offline))


if __name__ == '__main__':
    main()
