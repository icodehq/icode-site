#!/usr/bin/env python3
"""Build, check and serve the iCode static website.

Authored HTML lives in `public/`; shared chrome lives in `templates/`; locale
catalogs live in `i18n/`. Every authored page is rendered once per locale:
English stays at the site root, and each other locale is emitted under its
language code (`/zh-CN/`, `/ja/`, ...). The output is still a plain static
directory.

See `README.md` for the translation workflow.
"""

from __future__ import annotations

import argparse
import datetime
import html as html_text
import json
import os
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path

import i18n

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
TEMPLATES = ROOT / "templates"
I18N = ROOT / "i18n"
OUT = ROOT / "_site"

SITE_ORIGIN = (
    os.environ.get("SITE_ORIGIN")
    or (
        f"https://{os.environ['VERCEL_PROJECT_PRODUCTION_URL']}"
        if os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
        else "https://icodehq.com"
    )
).rstrip("/")

BUILD_YEAR = str(datetime.date.today().year)

# Region marker in a page -> template file whose rendered body replaces it.
REGIONS = {
    "site-header": "header.html.tmpl",
    "site-footer": "footer.html.tmpl",
}

SKIP_DIRS = {"__pycache__", ".venv", "node_modules", "_site"}

LOCALES = json.loads((I18N / "locales.json").read_text("utf-8"))
ENGLISH = next(locale for locale in LOCALES if locale["code"] == "en")


def route_key(route: str) -> str:
    return "home" if route == "" else route


def source_routes() -> dict[str, Path]:
    routes: dict[str, Path] = {}
    for path in sorted(PUBLIC.rglob("index.html")):
        rel = path.parent.relative_to(PUBLIC).as_posix()
        routes["" if rel == "." else rel] = path
    return routes


def catalog_path(code: str) -> Path:
    return I18N / f"{code}.json"


def load_catalog(code: str) -> dict:
    path = catalog_path(code)
    if not path.exists():
        raise SystemExit(f"missing translation catalog {path.relative_to(ROOT)}")
    return i18n.load_catalog(path)


def href_for(locale: dict, route: str) -> str:
    path = "" if route == "" else f"{route}/"
    return f"/{locale['code']}/{path}" if locale["code"] != "en" else f"/{path}"


def absolute_url(locale: dict, route: str) -> str:
    return SITE_ORIGIN + href_for(locale, route)


def language_menu(locale: dict, route: str, ui: dict) -> str:
    items = []
    for entry in LOCALES:
        current = ' aria-current="page"' if entry["code"] == locale["code"] else ""
        items.append(
            f'<li><a href="{href_for(entry, route)}" lang="{entry["htmlLang"]}"'
            f'{current}>{entry["label"]}</a></li>'
        )
    return (
        '<details class="language-menu">'
        f'<summary aria-label="{html_text.escape(ui["language.label"])}">'
        f'{locale["label"]}</summary>'
        f'<ul>{"".join(items)}</ul></details>'
    )


def head_links(locale: dict, route: str) -> str:
    links = [f'<link rel="canonical" href="{absolute_url(locale, route)}" />']
    for entry in LOCALES:
        links.append(
            f'<link rel="alternate" hreflang="{entry["htmlLang"]}" '
            f'href="{absolute_url(entry, route)}" />'
        )
    links.append(
        f'<link rel="alternate" hreflang="x-default" href="{absolute_url(ENGLISH, route)}" />'
    )
    return "\n  ".join(links)


def render_template(name: str, values: dict[str, str]) -> str:
    text = (TEMPLATES / name).read_text("utf-8")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise SystemExit(f"template {name}: unknown placeholder {{{{{key}}}}}")
        return values[key]

    return re.sub(r"\{\{([A-Za-z0-9_.-]+)\}\}", replace, text)


def inject_regions(html: str, locale: dict, route: str, ui: dict, href, language_menu_html):
    values = {
        "home_href": href(""),
        "workbench_href": href("workbench"),
        "agent_href": href("agent"),
        "guides_href": href("guides"),
        "blog_href": href("blog"),
        "faq_href": href("faq"),
        "about_href": href("about"),
        "get_started_href": href("get-started"),
        "github_url": "https://github.com/icodehq",
        "brand.caption": ui["brand.caption"],
        "nav.main": ui["nav.main"],
        "nav.workbench": ui["nav.workbench"],
        "nav.agent": ui["nav.agent"],
        "nav.guides": ui["nav.guides"],
        "nav.blog": ui["nav.blog"],
        "nav.faq": ui["nav.faq"],
        "nav.github": ui["nav.github"],
        "theme.toggle": ui["theme.toggle"],
        "language_menu": language_menu_html,
        "footer.tagline": ui["footer.tagline"],
        "footer.workbench": ui["footer.workbench"],
        "footer.agent": ui["footer.agent"],
        "footer.getStarted": ui["footer.getStarted"],
        "footer.guides": ui["footer.guides"],
        "footer.blog": ui["footer.blog"],
        "footer.faq": ui["footer.faq"],
        "footer.about": ui["footer.about"],
        "footer.github": ui["footer.github"],
        "footer.copy": ui["footer.copy"].replace(
            "{year}", f'<span data-year>{BUILD_YEAR}</span>'
        ),
        "authoritative_note": (
            ""
            if locale["code"] == "en"
            else f'<p class="translation-note">{ui["footer.authoritative"]}</p>'
        ),
    }
    for region, template in REGIONS.items():
        begin = f"<!-- BEGIN:{region} -->"
        end = f"<!-- END:{region} -->"
        if html.count(begin) != 1 or html.count(end) != 1:
            raise SystemExit(f"{locale['code']}/{route}: expected one {region} marker")
        body = render_template(template, values)
        html = re.sub(
            re.escape(begin) + r".*?" + re.escape(end),
            begin + "\n" + body + end,
            html,
            flags=re.DOTALL,
        )
    return html


def render_site_page(source: str, route: str, locale: dict, catalog: dict) -> str:
    return i18n.render_page(
        source,
        route_key(route),
        locale,
        catalog,
        catalog["ui"],
        href=lambda target: href_for(locale, target),
        language_menu=language_menu(locale, route, catalog["ui"]),
        head_links=head_links(locale, route),
        year=BUILD_YEAR,
        inject_regions=inject_regions,
    )


def extract_english(routes: dict[str, Path] | None = None) -> dict:
    return i18n.extract_site(PUBLIC, routes or source_routes())


def compare_english_catalog(fresh: dict, stored: dict) -> list[str]:
    issues: list[str] = []
    if set(fresh["pages"]) != set(stored.get("pages", {})):
        issues.append(
            "i18n/en.json: page set is stale (run `python3 scripts/site.py extract`)"
        )
        return issues
    for route in fresh["pages"]:
        source_page = fresh["pages"][route]
        stored_page = stored["pages"][route]
        for field in ("meta", "blocks", "alts"):
            if set(source_page[field]) != set(stored_page.get(field, {})):
                issues.append(
                    f"i18n/en.json: {route} {field} is stale "
                    "(run `python3 scripts/site.py extract`)"
                )
        for field in ("title", "description"):
            if source_page["meta"][field] != stored_page.get("meta", {}).get(field):
                issues.append(
                    f"i18n/en.json: {route} meta.{field} is stale "
                    "(run `python3 scripts/site.py extract`)"
                )
    return issues


def output_links_ok() -> list[str]:
    issues: list[str] = []
    for path in sorted(OUT.rglob("*.html")):
        rel = path.relative_to(OUT)
        meta = MetaReader()
        meta.feed(path.read_text("utf-8"))
        for target in meta.links:
            if re.match(r"^(https?:|mailto:|#|data:|tel:)", target):
                continue
            local = target.split("#", 1)[0].split("?", 1)[0]
            if not local:
                continue
            if local.startswith("/"):
                resolved = OUT / local.lstrip("/")
            else:
                resolved = path.parent / local
            if local.endswith("/") or resolved.is_dir():
                resolved = resolved / "index.html"
            if not resolved.exists():
                issues.append(f"{rel}: broken link {target}")
    return issues


def check_sources() -> None:
    issues: list[str] = []
    for path in sorted(PUBLIC.rglob("*.html")):
        rel = path.relative_to(PUBLIC)
        text = path.read_text("utf-8")
        for region in REGIONS:
            if text.count(f"<!-- BEGIN:{region} -->") != 1:
                issues.append(f"{rel}: missing or duplicated BEGIN:{region}")
            if text.count(f"<!-- END:{region} -->") != 1:
                issues.append(f"{rel}: missing or duplicated END:{region}")
        meta = MetaReader()
        meta.feed(text)
        if not meta.title.strip():
            issues.append(f"{rel}: missing <title>")
        if not meta.description.strip():
            issues.append(f"{rel}: missing meta description")
        for target in meta.links:
            if re.match(r"^(https?:|mailto:|#|data:)", target):
                continue
            local = target.split("#", 1)[0].split("?", 1)[0]
            if not local:
                continue
            resolved = (path.parent / local).resolve()
            if not resolved.exists():
                issues.append(f"{rel}: broken link {target}")
    if issues:
        raise SystemExit("Website check failed:\n- " + "\n- ".join(issues))


def check_catalogs() -> None:
    routes = source_routes()
    fresh = extract_english(routes)
    stored = load_catalog("en")
    issues = compare_english_catalog(fresh, stored)
    catalogs = {"en": stored}
    for locale in LOCALES:
        if locale["code"] == "en":
            continue
        catalogs[locale["code"]] = load_catalog(locale["code"])
    issues += i18n.validate(stored, catalogs)
    if issues:
        raise SystemExit("Translation check failed:\n- " + "\n- ".join(issues))


def build() -> None:
    routes = source_routes()
    fresh = extract_english(routes)
    english = load_catalog("en")
    issues = compare_english_catalog(fresh, english)
    catalogs = {"en": english}
    for locale in LOCALES:
        if locale["code"] == "en":
            continue
        catalogs[locale["code"]] = load_catalog(locale["code"])
    issues += i18n.validate(english, catalogs)
    if issues:
        raise SystemExit("Build stopped:\n- " + "\n- ".join(issues))

    if OUT.exists():
        shutil.rmtree(OUT)

    # Shared, non-localized assets are copied once at the site root.
    for src in sorted(PUBLIC.rglob("*")):
        rel = src.relative_to(PUBLIC)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if src.is_dir() or src.suffix == ".html":
            continue
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == ".txt":
            dest.write_text(
                src.read_text("utf-8").replace("${site_origin}", SITE_ORIGIN),
                "utf-8",
            )
        else:
            shutil.copy2(src, dest)

    for locale in LOCALES:
        catalog = catalogs[locale["code"]]
        for route, src_path in routes.items():
            html = render_site_page(src_path.read_text("utf-8"), route, locale, catalog)
            dest = OUT / ("" if locale["code"] == "en" else locale["code"]) / route
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "index.html").write_text(html, "utf-8")

    write_sitemap(routes)
    issues = output_links_ok()
    if issues:
        raise SystemExit("Built-site link check failed:\n- " + "\n- ".join(issues))
    print(f"Built {OUT.relative_to(ROOT)} ({len(LOCALES)} locales, {len(routes)} routes)")


def write_sitemap(routes: dict[str, Path]) -> None:
    entries: list[str] = []
    for route in sorted(routes):
        alternates = "\n".join(
            f'    <xhtml:link rel="alternate" hreflang="{locale["htmlLang"]}" '
            f'href="{absolute_url(locale, route)}" />'
            for locale in LOCALES
        )
        default = (
            f'    <xhtml:link rel="alternate" hreflang="x-default" '
            f'href="{absolute_url(ENGLISH, route)}" />'
        )
        for locale in LOCALES:
            entries.append(
                f"  <url>\n"
                f"    <loc>{absolute_url(locale, route)}</loc>\n"
                f"{alternates}\n{default}\n"
                f"  </url>"
            )
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        f'{"".join(entries)}\n</urlset>\n',
        "utf-8",
    )


class MetaReader(HTMLParser):
    """Read title and description, and collect local link targets."""

    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.title = ""
        self.description = ""
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and (a.get("name") or "").lower() == "description":
            self.description = a.get("content") or ""
        for attr in ("href", "src"):
            value = a.get(attr)
            if value:
                self.links.append(value)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def check() -> None:
    check_sources()
    check_catalogs()
    print("Checked source pages and translation catalogs: OK")


def serve(host: str, port: int) -> None:
    import http.server

    if not OUT.exists():
        build()
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *a, directory=str(OUT), **k
    )
    with http.server.ThreadingHTTPServer((host, port), handler) as httpd:
        shown = "localhost" if host in ("0.0.0.0", "::") else host
        print(f"Serving http://{shown}:{port}/ (bound to {host}, Ctrl-C to stop)")
        httpd.serve_forever()


def extract() -> None:
    data = extract_english()
    path = catalog_path("en")
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        "utf-8",
    )
    blocks = sum(len(page["blocks"]) for page in data["pages"].values())
    alts = sum(len(page["alts"]) for page in data["pages"].values())
    print(
        f"Extracted {len(data['pages'])} pages, {blocks} blocks, {alts} alt texts "
        f"to {path.relative_to(ROOT)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    sub.add_parser("check")
    sub.add_parser("deploy-check")
    sub.add_parser("extract")
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()

    if args.command == "build":
        build()
    elif args.command == "check":
        check()
    elif args.command == "extract":
        extract()
    elif args.command == "deploy-check":
        check()
        build()
    elif args.command == "serve":
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
