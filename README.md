# Sapere Aude

Static version of the blog formerly at kangyan.bearblog.dev, served by
Cloudflare Pages straight from this repo (push to `main` deploys).

```
index.html            home
blog/                 博文   (full archive)
twix/                 閒話   (+ twix/2024/, twix/2025/ archives)
movies/               影冊
games/                遊戲
arxiv/                資料庫
posts/                every article and 專欄 page, at its Bear path
                      e.g. posts/travel/hawaii/, posts/eatstory/02/
assets/               style.css, scripts, images/
_redirects            old Bear-style URLs -> new locations (301)
tools/import_bear.py  re-imports from Bear and rebuilds all of the above
```

## Re-importing from Bear

```
python3 tools/import_bear.py            # download from Bear, rebuild
python3 tools/import_bear.py --offline  # rebuild from the last download (.bear-cache/)
```

The importer regenerates every page and `_redirects`. Hand edits to generated
pages are lost on re-import unless they are also listed in `EDITS` in
`tools/import_bear.py`, which re-applies them on every build.
