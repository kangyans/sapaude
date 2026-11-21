#!/usr/bin/env python3
"""Import kangyan.bearblog.dev into this static site.

Downloads the Bear pages (home, 博文, 閒話, 資料庫, 影冊, 遊戲, every post and
every internal page they link to), then rewrites them into the site's own
layout under the repo root, keeping Bear's URLs.

Usage (from anywhere):
    python3 tools/import_bear.py            # fetch fresh copies, then build
    python3 tools/import_bear.py --offline  # rebuild from the cached download

Downloads are cached in .bear-cache/ (git-ignored). Only the standard library
is used. Images in the pages are downloaded once into assets/images/ (named by
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
CACHE = os.path.join(REPO, '.bear-cache')
IMAGES = os.path.join(REPO, 'assets', 'images')
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

# Folder layout: home and each nav section keep their own top-level folder;
# 閒話 archives live under twix/; every article (posts, series pages) lives
# under posts/ at its Bear path. Old Bear URLs are forwarded by _redirects.
SECTION_MOVES = {'/archive/twix/2025/': '/twix/2025/'}


def site_path(p):
    """Bear path -> path in this site."""
    if p == '/' or p in SECTIONS or p.startswith('/twix/'):
        return p
    if p in SECTION_MOVES:
        return SECTION_MOVES[p]
    return '/posts' + p


# Long texts set as books (see "Book reader" in style.css, assets/book.js).
# A series book: its Bear index page becomes the cover + contents, and each
# chapter page gets a running head, page-turn links and the reading bar.
BOOKS = [
    {'id': 'renjian', 'index': '/classic/renjian/', 'title': '人間詞話', 'author': '王國維',
     'chapters': ['/poems/01/', '/poems/02/', '/poems/03/', '/poems/04/']},
    {'id': 'luyou', 'index': '/classic/luyou/', 'title': '放翁詞編年箋注選', 'author': '陸游',
     'chapters': ['/classic/luyou/01/', '/classic/luyou/02/', '/classic/luyou/03/']},
    {'id': 'eatstory', 'index': '/eatstory/', 'title': '食林廣記', 'author': None,
     'chapters': ['/eatstory/01/', '/eatstory/02/', '/eatstory/03/', '/eatstory/04/'],
     'labels': ['自序', '卷一', '卷二', '卷三']},
]
# One-page books: a title page and the reading bar.
SINGLE_BOOKS = {
    '/4325/': {'id': 'baorenan', 'title': '報任安書', 'author': '司馬遷', 'kicker': '箋注'},
}
ZH_NUM = '一二三四五六七八九十'

# Hand edits made to generated pages, re-applied on every build so a
# re-import never undoes them: (site path, regex, replacement).
EDITS = [
    # 2026-11-21: 鳴謝 trimmed to its first two sentences, P.S. dropped
    ('/arxiv/',
     r'的內容。他做的非常好.*?</p>\s*<p><em><strong>P\.S\.</strong></em>.*?</p>',
     '的內容。</p>'),
]


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
                new = site_path(norm(path)) + ('#' + frag if frag else '')
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
    path = site_path(path)
    for where, pattern, repl in EDITS:
        if where == path:
            doc, n = re.subn(pattern, repl, doc, count=1, flags=re.S)
            if not n:
                print(f'  hand edit not applied on {path} (source text changed?): {pattern[:40]}…')
    out = os.path.join(REPO, path.strip('/'), 'index.html')
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


def roman(n):
    out = ''
    for v, r in ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'),
                 (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')):
        while n >= v:
            out += r
            n -= v
    return out


def enchiridion_book(m):
    """The Enchiridion: the Bear post is the MIT Classics text pasted inside a
    <pre>. Rebuild it as a book: title page, contents, 52 numbered chapters,
    colophon. assets/book.js adds the reading bar, progress and resume."""
    items = re.findall(r'<li>(.*?)</li>', m, re.S)
    if not items:
        return None

    def tidy(x):
        x = re.sub(r'\s+', ' ', x).strip()
        return x.replace(' 0 ', ' O ').replace('"0 ', '"O ')   # source typed "0" for the vocative "O"

    chapters = []
    for i, body in enumerate(items, 1):
        paras = [tidy(p) for p in re.findall(r'<p>(.*?)</p>', body, re.S)] or [tidy(body)]
        first = re.sub(r'<[^>]+>', '', paras[0])
        words = first.split()
        incipit = ' '.join(words[:7]) + ('…' if len(words) > 7 else '')
        chapters.append((i, paras, html.escape(incipit, quote=False)))

    n = len(chapters)
    toc = '\n'.join(f'<li><a href="#ch-{i}"><span class="toc-no">{roman(i)}</span>'
                    f'<span class="toc-incipit">{inc}</span></a></li>' for i, _, inc in chapters)
    body = []
    for i, paras, _ in chapters:
        ps = '\n'.join(f'<p>{p}</p>' for p in paras)
        body.append(f'<section class="chapter" id="ch-{i}" data-no="{roman(i)}">\n'
                    f'<h2 class="chapter-no"><span class="visually-hidden">Chapter </span>{roman(i)}</h2>\n{ps}\n</section>')
    colo = re.search(r'Copyright statement:(.*?)</pre>', m, re.S)
    colophon = tidy(colo.group(1)) if colo else ''
    return f'''<article class="book" lang="en" data-chapters="{n}" data-book="enchiridion" data-book-title="The Enchiridion">
<header class="book-title">
<p class="book-kicker">開源閱讀</p>
<h1 class="book-name">The Enchiridion</h1>
<p class="book-author">Epictetus</p>
<p class="book-translator">Translated by Elizabeth Carter</p>
</header>

<nav class="book-toc" id="contents" aria-label="Contents">
<h2 class="book-toc-title">Contents</h2>
<p class="book-resume" hidden></p>
<ol class="toc-list">
{toc}
</ol>
</nav>

<div class="book-text">
{chr(10).join(body)}
<p class="book-end">The End</p>
</div>

<footer class="book-colophon">
<p>Text: <a href="http://classics.mit.edu/Epictetus/epicench.html">The Internet Classics Archive</a>.
{colophon}</p>
</footer>
</article>'''


def book_chapters(book):
    """[(bear path, label, incipit)] for a series book, read from the cache."""
    key = re.sub(r'[\s·・]', '', book['title'])
    labels = book.get('labels') or [f'卷{ZH_NUM[i]}' for i in range(len(book['chapters']))]
    out = []
    for path, label in zip(book['chapters'], labels):
        mm = re.sub(r'<style.*?</style>', '', main_of(read(cache_file(path))), flags=re.S)
        heads = [re.sub(r'<[^>]+>', '', h).strip() for h in re.findall(r'<h[23][^>]*>(.*?)</h[23]>', mm, re.S)]
        heads = [h for h in heads if h and key not in re.sub(r'[\s·・]', '', h)]
        inc = re.sub(r'^【(.*)】$', r'\1', re.sub(r'\s+', ' ', heads[0])) if heads else ''
        if not inc or inc == label:          # e.g. 自序 headed 【自序】: use its opening words
            body = re.sub(r'<(script|form|h[1-3])\b.*?</\1>|<time\b.*?</time>', '', mm, flags=re.S)
            text = re.sub(r'\s+', '', re.sub(r'<[^>]+>', '', body))
            inc = text[:16] + '…'
        out.append((path, label, html.escape(inc, quote=False)))
    return out


def book_cover(book, chapters, note):
    lis = '\n'.join(f'<li><a href="{site_path(p)}"><span class="toc-no">{label}</span>'
                    f'<span class="toc-incipit">{inc}</span></a></li>' for p, label, inc in chapters)
    author = f'<p class="book-author">{book["author"]}</p>\n' if book.get('author') else ''
    note = f'<p class="book-note">{note}</p>\n' if note else ''
    return f'''<article class="book book-zh book-cover" data-book="{book['id']}" data-book-title="{book['title']}">
<header class="book-title">
<p class="book-kicker">專欄</p>
<h1 class="book-name">{book['title']}</h1>
{author}{note}</header>
<nav class="book-toc" id="contents" aria-label="目錄">
<h2 class="book-toc-title">目錄</h2>
<p class="book-resume" hidden></p>
<ol class="toc-list toc-zh">
{lis}
</ol>
</nav>
</article>'''


def book_chapter_page(book, chapters, i, body):
    """Wrap one chapter: running head on top, page-turn links at the bottom."""
    body = re.sub(r'<div class="navigation-container">.*?</div>', '', body, flags=re.S)
    path, label, _ = chapters[i]
    index = site_path(book['index'])
    prev = (f'<a class="pager-prev" href="{site_path(chapters[i - 1][0])}">‹ {chapters[i - 1][1]}</a>'
            if i > 0 else '<span class="pager-prev"></span>')
    nxt = (f'<a class="pager-next" href="{site_path(chapters[i + 1][0])}">{chapters[i + 1][1]} ›</a>'
           if i + 1 < len(chapters) else '<span class="pager-next"></span>')
    return (f'<article class="book-page book-zh" data-book="{book["id"]}" data-book-title="{book["title"]}" '
            f'data-label="{label}　{i + 1} / {len(chapters)}" data-toc="{index}">\n'
            f'<p class="book-running"><a href="{index}">{book["title"]}</a><span>{label}</span></p>\n'
            f'{body}\n'
            f'<nav class="book-pager" aria-label="翻頁">{prev}<a class="pager-toc" href="{index}">目錄</a>{nxt}</nav>\n'
            '</article>')


def book_single_page(meta, body):
    """One-page book: the post header becomes a title page."""
    dt = re.search(r'<time datetime="([^"]+)">([^<]*)</time>', body)
    date = f'<p class="book-date"><time datetime="{dt.group(1)}">{dt.group(2)}</time></p>\n' if dt else ''
    body = re.sub(r'<header class="post-header">.*?</header>\s*', '', body, count=1, flags=re.S)
    return (f'<article class="book-page book-zh" data-book="{meta["id"]}" data-book-title="{meta["title"]}" '
            f'data-label="{meta.get("kicker", "")}" data-toc="#top">\n'
            f'<header class="book-title" id="top">\n<p class="book-kicker">{meta.get("kicker", "")}</p>\n'
            f'<h1 class="book-name">{meta["title"]}</h1>\n<p class="book-author">{meta["author"]}</p>\n{date}</header>\n'
            f'{body}\n</article>')


def twix_datelines(m):
    """閒話: normalise each note's '公佈於 MM/DD/YYYY' to '公佈於 YYYY/MM/DD'."""
    def rep(x):
        mo, d, y = x.group(1), x.group(2), x.group(3)
        return (f'<p class="twix-date">公佈於 <time datetime="{y}-{mo}-{d}">{y}/{mo}/{d}</time>')
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
        if p == '/the-enchiridion/':
            book = enchiridion_book(m)
            if book:
                out(p, 'The Enchiridion', book, '<script src="/assets/book.js" defer></script>\n')
                continue
        book_script = '<script src="/assets/book.js" defer></script>\n'
        series = next((b for b in BOOKS if b['index'] == p), None)
        if series:
            note = re.search(r'<p>([^<]*連載[^<]*)</p>', m)
            out(p, series['title'], book_cover(series, book_chapters(series), note.group(1) if note else ''),
                book_script)
            continue
        series = next((b for b in BOOKS if p in b['chapters']), None)
        if series:
            body = book_chapter_page(series, book_chapters(series), series['chapters'].index(p), body)
            vscript += book_script
        if p in SINGLE_BOOKS:
            body = book_single_page(SINGLE_BOOKS[p], body)
            vscript += book_script
        if p == '/archive/twix/2025/':          # same note style as /twix/
            body = twix_datelines(body)
        out(p, re.sub('<[^>]+>', '', title), body, vscript)

    groups = OrderedDict()
    entries = [e for e in blog_entries(read(cache_file('/blog/'))) if e[1] not in EXCLUDE]
    for dt, href, name in entries:
        groups.setdefault(dt[:4], []).append((dt[5:10], site_path(href), name))
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

    # _redirects (Cloudflare Pages): old Bear-style URLs -> new locations
    lines = ['# Generated by tools/import_bear.py: old URLs -> current locations']
    for p in ok:
        new = site_path(p)
        if new != p:
            lines += [f'{p} {new} 301', f'{p.rstrip("/")} {new} 301']
    with open(os.path.join(REPO, '_redirects'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

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
