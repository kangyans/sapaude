# Sapere Aude

Static version of the blog formerly at kangyan.bearblog.dev.

```
site/        everything that is published (Cloudflare Pages build output directory)
  index.html, blog/, twix/, movies/, games/, arxiv/   home and sections
  <post paths>/                                       posts, at their Bear URLs
  assets/    style.css, calendar.js, vertical.js, rows.js, images/
tools/
  import_bear.py   re-imports content from Bear and rebuilds site/
```

## Deploying

Pushing to `main` deploys: Cloudflare Pages serves `site/` as-is (no build command).

## Re-importing from Bear

```
python3 tools/import_bear.py            # download from Bear, rebuild site/
python3 tools/import_bear.py --offline  # rebuild from the last download (.bear-cache/)
```

The importer regenerates every page in `site/`, so make content changes on Bear
(or in the importer), not by editing the generated HTML. Design lives in
`site/assets/style.css`.
