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
import struct
import sys
import unicodedata
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

OG_DEFAULT_PATH = "/assets/social/og-default-1200x630.png"
OG_WIDTH = 1200
OG_HEIGHT = 630
OG_ALT_KEY = "social.imageAlt"
ARTICLE_ROUTES = {
    "blog/context-management",
    "blog/agent-review-workflow",
    "blog/agent-task-queue",
    "blog/mira-cross-project-assistant",
    "guides/parallel-agents",
    "guides/fix-a-failing-test",
    "guides/refactor-a-module",
    "guides/track-down-a-bug",
    "guides/automate-in-ci",
    "guides/what-is-an-agent-development-environment",
    "guides/from-one-agent-to-a-fleet",
}

# Routes that exist only in English. They are built once, canonicalized to the
# English URL, and omitted from the localized builds and hreflang alternates.
ENGLISH_ONLY_ROUTES = {
    "guides/parallel-agents",
    "guides/what-is-an-agent-development-environment",
    "guides/from-one-agent-to-a-fleet",
    "compare/orca",
    "blog/agent-review-workflow",
    "blog/agent-task-queue",
    "blog/mira-cross-project-assistant",
}

# Update a route only when its page content actually changes. These dates drive
# sitemap <lastmod> and TechArticle dateModified; they must not follow the build.
CONTENT_DATES = {
    "": "2026-11-23",
    "workbench": "2026-11-23",
    "agent": "2026-11-23",
    "about": "2026-11-23",
    "faq": "2026-11-23",
    "get-started": "2026-11-09",
    "first-investigation": "2026-11-09",
    "blog": "2026-11-09",
    "blog/context-management": "2026-11-23",
    "blog/agent-review-workflow": "2026-11-23",
    "blog/agent-task-queue": "2026-11-23",
    "blog/mira-cross-project-assistant": "2026-11-23",
    "guides": "2026-11-09",
    "guides/parallel-agents": "2026-11-23",
    "guides/fix-a-failing-test": "2026-11-23",
    "guides/refactor-a-module": "2026-11-23",
    "guides/track-down-a-bug": "2026-11-23",
    "guides/automate-in-ci": "2026-11-23",
    "guides/what-is-an-agent-development-environment": "2026-11-24",
    "guides/from-one-agent-to-a-fleet": "2026-11-24",
    "compare/orca": "2026-11-24",
}
ARTICLE_PUBLISHED = {
    "blog/context-management": "2026-10-14",
    "blog/agent-review-workflow": "2026-11-23",
    "blog/agent-task-queue": "2026-11-23",
    "blog/mira-cross-project-assistant": "2026-11-23",
    "guides/parallel-agents": "2026-11-23",
    "guides/fix-a-failing-test": "2026-10-14",
    "guides/refactor-a-module": "2026-10-14",
    "guides/track-down-a-bug": "2026-10-14",
    "guides/automate-in-ci": "2026-10-14",
    "guides/what-is-an-agent-development-environment": "2026-11-24",
    "guides/from-one-agent-to-a-fleet": "2026-11-24",
}
PRODUCTS = {
    "workbench": {
        "name": "iCode Workbench",
        "operatingSystem": "Windows, Linux, macOS",
        "license": "https://www.gnu.org/licenses/agpl-3.0.html",
        "codeRepository": "https://github.com/icodehq/icode-workbench",
    },
    "agent": {
        "name": "iCode Agent",
        "operatingSystem": "Windows, macOS, Linux",
        "license": "https://www.apache.org/licenses/LICENSE-2.0",
        "codeRepository": "https://github.com/icodehq/icode-agent",
    },
}


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
    if route in ENGLISH_ONLY_ROUTES:
        return f"/{route}/"
    path = "" if route == "" else f"{route}/"
    return f"/{locale['code']}/{path}" if locale["code"] != "en" else f"/{path}"


def absolute_url(locale: dict, route: str) -> str:
    return SITE_ORIGIN + href_for(locale, route)


def language_menu(locale: dict, route: str, ui: dict) -> str:
    if route in ENGLISH_ONLY_ROUTES:
        return ""
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
    if route in ENGLISH_ONLY_ROUTES:
        links.append(
            f'<link rel="alternate" hreflang="en" '
            f'href="{absolute_url(ENGLISH, route)}" />'
        )
        links.append(
            f'<link rel="alternate" hreflang="x-default" '
            f'href="{absolute_url(ENGLISH, route)}" />'
        )
        return "\n  ".join(links)
    for entry in LOCALES:
        links.append(
            f'<link rel="alternate" hreflang="{entry["htmlLang"]}" '
            f'href="{absolute_url(entry, route)}" />'
        )
    links.append(
        f'<link rel="alternate" hreflang="x-default" href="{absolute_url(ENGLISH, route)}" />'
    )
    return "\n  ".join(links)


def _attr(value: str) -> str:
    return html_text.escape(str(value), quote=True)


def _og_locale(locale: dict) -> str:
    return locale["ogLocale"]


def _og_image() -> str:
    return SITE_ORIGIN + OG_DEFAULT_PATH


def hero_preload(route: str) -> str:
    if route not in ("", "workbench"):
        return ""
    srcset = (
        "/assets/workbench/shell-640.avif 640w, "
        "/assets/workbench/shell-1280.avif 1280w, "
        "/assets/workbench/shell-1600.avif 1600w"
    )
    return (
        '<link rel="preload" as="image" type="image/avif" fetchpriority="high" '
        'href="/assets/workbench/shell-1280.avif" '
        f'imagesrcset="{srcset}" '
        'imagesizes="(max-width: 808px) calc(100vw - 3rem), 712px" />'
    )


def social_meta(locale: dict, route: str, meta: dict, ui: dict) -> str:
    page_url = absolute_url(locale, route)
    image = _og_image()
    og_type = "article" if route in ARTICLE_ROUTES else "website"
    alt = ui[OG_ALT_KEY]
    lines = [
        '<meta property="og:site_name" content="iCode" />',
        f'<meta property="og:type" content="{og_type}" />',
        f'<meta property="og:title" content="{_attr(meta["title"])}" />',
        f'<meta property="og:description" content="{_attr(meta["description"])}" />',
        f'<meta property="og:url" content="{_attr(page_url)}" />',
        f'<meta property="og:locale" content="{_attr(_og_locale(locale))}" />',
    ]
    if route not in ENGLISH_ONLY_ROUTES:
        for entry in LOCALES:
            if entry["code"] != locale["code"]:
                lines.append(
                    f'<meta property="og:locale:alternate" '
                    f'content="{_attr(entry["ogLocale"])}" />'
                )
    lines += [
        f'<meta property="og:image" content="{_attr(image)}" />',
        f'<meta property="og:image:secure_url" content="{_attr(image)}" />',
        '<meta property="og:image:type" content="image/png" />',
        f'<meta property="og:image:width" content="{OG_WIDTH}" />',
        f'<meta property="og:image:height" content="{OG_HEIGHT}" />',
        f'<meta property="og:image:alt" content="{_attr(alt)}" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{_attr(meta["title"])}" />',
        f'<meta name="twitter:description" content="{_attr(meta["description"])}" />',
        f'<meta name="twitter:image" content="{_attr(image)}" />',
        f'<meta name="twitter:image:alt" content="{_attr(alt)}" />',
    ]
    return "\n  ".join(lines)


def _json_ld(data: dict) -> str:
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    text = (
        text.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
    return f'<script type="application/ld+json">{text}</script>'


def json_ld(locale: dict, route: str, meta: dict, ui: dict) -> str:
    page_url = absolute_url(locale, route)
    image_url = _og_image()
    org_id = SITE_ORIGIN + "/#organization"
    site_id = SITE_ORIGIN + "/#website"
    page_id = page_url + "#webpage"
    page_node = {
        "@type": "WebPage",
        "@id": page_id,
        "url": page_url,
        "name": meta["title"],
        "description": meta["description"],
        "inLanguage": locale["htmlLang"],
        "isPartOf": {"@id": site_id},
        "publisher": {"@id": org_id},
        "primaryImageOfPage": {
            "@type": "ImageObject",
            "url": image_url,
            "width": OG_WIDTH,
            "height": OG_HEIGHT,
        },
    }
    if route in PRODUCTS:
        page_node["mainEntity"] = {"@id": page_url + "#software"}
    elif route in ARTICLE_ROUTES:
        page_node["mainEntity"] = {"@id": page_url + "#article"}

    graph = [
        {
            "@type": "Organization",
            "@id": org_id,
            "name": "iCode",
            "url": SITE_ORIGIN + "/",
            "logo": SITE_ORIGIN + "/assets/logo.svg",
            "sameAs": ["https://github.com/icodehq"],
        },
        {
            "@type": "WebSite",
            "@id": site_id,
            "url": SITE_ORIGIN + "/",
            "name": "iCode",
            "publisher": {"@id": org_id},
        },
        page_node,
    ]

    if route != "":
        items = [
            {"@type": "ListItem", "position": 1, "name": "iCode", "item": SITE_ORIGIN + "/"}
        ]
        if "/" in route:
            section = route.split("/", 1)[0]
            if section == "guides":
                label = ui["nav.guides"]
            elif section == "blog":
                label = ui["nav.blog"]
            else:
                label = section.replace("-", " ").title()
            items.append(
                {
                    "@type": "ListItem",
                    "position": len(items) + 1,
                    "name": label,
                    "item": absolute_url(locale, section),
                }
            )
        items.append(
            {
                "@type": "ListItem",
                "position": len(items) + 1,
                "name": meta["title"],
                "item": page_url,
            }
        )
        graph.append(
            {
                "@type": "BreadcrumbList",
                "@id": page_url + "#breadcrumb",
                "itemListElement": items,
            }
        )

    if route in PRODUCTS:
        product = PRODUCTS[route]
        graph.append(
            {
                "@type": "SoftwareApplication",
                "@id": page_url + "#software",
                "name": product["name"],
                "description": meta["description"],
                "url": page_url,
                "applicationCategory": "DeveloperApplication",
                "operatingSystem": product["operatingSystem"],
                "isAccessibleForFree": True,
                "license": product["license"],
                "codeRepository": product["codeRepository"],
                "publisher": {"@id": org_id},
                "mainEntityOfPage": {"@id": page_id},
                "screenshot": image_url,
            }
        )

    if route in ARTICLE_ROUTES:
        graph.append(
            {
                "@type": "TechArticle",
                "@id": page_url + "#article",
                "headline": meta["title"],
                "description": meta["description"],
                "inLanguage": locale["htmlLang"],
                "url": page_url,
                "image": image_url,
                "datePublished": ARTICLE_PUBLISHED[route],
                "dateModified": CONTENT_DATES[route],
                "author": {"@id": org_id},
                "publisher": {"@id": org_id},
                "mainEntityOfPage": {"@id": page_id},
                "isPartOf": {"@id": site_id},
            }
        )

    return _json_ld({"@context": "https://schema.org", "@graph": graph})


def head_extra(locale: dict, route: str, meta: dict, ui: dict) -> str:
    parts = [
        hero_preload(route),
        head_links(locale, route),
        social_meta(locale, route, meta, ui),
        json_ld(locale, route, meta, ui),
    ]
    return "\n  ".join(part for part in parts if part)


def split_srcset(value: str) -> list[str]:
    return [part.strip().split()[0] for part in value.split(",") if part.strip()]


def display_width(value: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in value
    )


def check_meta_lengths(catalogs: dict) -> list[str]:
    warnings: list[str] = []
    for code, catalog in catalogs.items():
        for route, page in catalog.get("pages", {}).items():
            meta = page.get("meta", {})
            for field, limit in (("title", 60), ("description", 160)):
                value = str(meta.get(field, ""))
                width = display_width(value)
                if width > limit:
                    warnings.append(
                        f"i18n/{code}: {route} meta.{field} is {width} "
                        f"display columns (limit {limit})"
                    )
    return warnings


def check_locales() -> None:
    issues: list[str] = []
    seen: set[str] = set()
    for locale in LOCALES:
        value = locale.get("ogLocale", "")
        if not re.match(r"^[a-z]{2,3}_[A-Z]{2}$", value):
            issues.append(
                f"i18n/locales.json: {locale.get('code', '?')} has invalid "
                f"ogLocale {value!r}"
            )
        if value in seen:
            issues.append(f"i18n/locales.json: duplicate ogLocale {value!r}")
        seen.add(value)
    if issues:
        raise SystemExit("Locale check failed:\n- " + "\n- ".join(issues))


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


def webp_ok(path: Path) -> bool:
    data = path.read_bytes()
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def avif_ok(path: Path) -> bool:
    data = path.read_bytes()
    return (
        len(data) >= 12
        and data[4:8] == b"ftyp"
        and (b"avif" in data[:64] or b"avis" in data[:64])
    )


def check_social_assets() -> None:
    issues: list[str] = []
    og_path = PUBLIC / OG_DEFAULT_PATH.lstrip("/")
    shell_path = PUBLIC / "assets" / "workbench" / "shell.png"

    if not og_path.exists():
        issues.append(f"missing {og_path.relative_to(ROOT)}")
    else:
        try:
            dimensions = png_dimensions(og_path)
        except ValueError as exc:
            issues.append(f"{og_path.relative_to(ROOT)}: {exc}")
        else:
            if dimensions != (OG_WIDTH, OG_HEIGHT):
                issues.append(
                    f"{og_path.relative_to(ROOT)}: {dimensions[0]}x{dimensions[1]}, "
                    f"expected {OG_WIDTH}x{OG_HEIGHT}"
                )
            if og_path.stat().st_size > 300_000:
                issues.append(f"{og_path.relative_to(ROOT)} is larger than 300 KB")

    if not shell_path.exists():
        issues.append(f"missing {shell_path.relative_to(ROOT)}")
    else:
        try:
            dimensions = png_dimensions(shell_path)
        except ValueError as exc:
            issues.append(f"{shell_path.relative_to(ROOT)}: {exc}")
        else:
            if dimensions != (1600, 1000):
                issues.append(
                    f"{shell_path.relative_to(ROOT)}: {dimensions[0]}x{dimensions[1]}, "
                    "expected 1600x1000"
                )
        shell_size = shell_path.stat().st_size
        for width in (640, 1280, 1600):
            for ext, checker in (("webp", webp_ok), ("avif", avif_ok)):
                path = PUBLIC / "assets" / "workbench" / f"shell-{width}.{ext}"
                if not path.exists():
                    issues.append(f"missing {path.relative_to(ROOT)}")
                elif not checker(path):
                    issues.append(f"{path.relative_to(ROOT)} is not a valid {ext.upper()}")
                elif path.stat().st_size >= shell_size:
                    issues.append(
                        f"{path.relative_to(ROOT)} is not smaller than shell.png"
                    )

    if issues:
        raise SystemExit("Social asset check failed:\n- " + "\n- ".join(issues))


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
        "compare_href": href_for(locale, "compare/orca"),
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
        "nav.compare": ui["nav.compare"],
        "nav.faq": ui["nav.faq"],
        "nav.github": ui["nav.github"],
        "theme.toggle": ui["theme.toggle"],
        "language_menu": language_menu_html,
        "article.meta": (
            ui["article.meta"].format(
                published=ARTICLE_PUBLISHED[route],
                updated=CONTENT_DATES[route],
            )
            if route in ARTICLE_ROUTES
            else ""
        ),
        "footer.tagline": ui["footer.tagline"],
        "footer.workbench": ui["footer.workbench"],
        "footer.agent": ui["footer.agent"],
        "footer.getStarted": ui["footer.getStarted"],
        "footer.guides": ui["footer.guides"],
        "footer.blog": ui["footer.blog"],
        "footer.compare": ui["footer.compare"],
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
    if route in ARTICLE_ROUTES:
        begin = "<!-- BEGIN:article-meta -->"
        end = "<!-- END:article-meta -->"
        if html.count(begin) != 1 or html.count(end) != 1:
            raise SystemExit(
                f"{locale['code']}/{route}: expected one article-meta marker"
            )
        body = render_template("article-meta.html.tmpl", values)
        html = re.sub(
            re.escape(begin) + r".*?" + re.escape(end),
            begin + "\n" + body + end,
            html,
            flags=re.DOTALL,
        )
    return html


def render_site_page(source: str, route: str, locale: dict, catalog: dict) -> str:
    page_meta = catalog["pages"][route_key(route)]["meta"]
    return i18n.render_page(
        source,
        route_key(route),
        locale,
        catalog,
        catalog["ui"],
        href=lambda target: href_for(locale, target),
        language_menu=language_menu(locale, route, catalog["ui"]),
        head_extra=head_extra(locale, route, page_meta, catalog["ui"]),
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
        targets = list(meta.links)
        for value in meta.srcsets:
            targets.extend(split_srcset(value))
        for key in ("og:image", "og:image:secure_url", "twitter:image"):
            targets.extend(meta.meta_props.get(key, []))
        for target in targets:
            if target == SITE_ORIGIN:
                target = "/"
            elif target.startswith(SITE_ORIGIN + "/"):
                target = target[len(SITE_ORIGIN) :]
            elif re.match(r"^(https?:|mailto:|#|data:|tel:)", target):
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


def social_meta_ok() -> list[str]:
    issues: list[str] = []
    locale_by_code = {locale["code"]: locale for locale in LOCALES}
    required = (
        "og:site_name",
        "og:type",
        "og:title",
        "og:description",
        "og:url",
        "og:locale",
        "og:image",
        "og:image:secure_url",
        "og:image:type",
        "og:image:width",
        "og:image:height",
        "og:image:alt",
        "twitter:card",
        "twitter:title",
        "twitter:description",
        "twitter:image",
        "twitter:image:alt",
    )

    for path in sorted(OUT.rglob("index.html")):
        rel = path.relative_to(OUT)
        parts = rel.as_posix().split("/")[:-1]
        code = parts[0] if parts and parts[0] in locale_by_code else "en"
        route = "/".join(parts[1:]) if code != "en" else "/".join(parts)
        locale = locale_by_code[code]
        page = rel.as_posix()
        meta = MetaReader()
        meta.feed(path.read_text("utf-8"))

        expected_url = absolute_url(locale, route)
        if len(meta.canonicals) != 1 or meta.canonicals[0] != expected_url:
            issues.append(f"{page}: canonical mismatch")

        for key in required:
            values = meta.meta_props.get(key, [])
            if len(values) != 1:
                issues.append(f"{page}: expected one {key}, found {len(values)}")

        def prop(key: str) -> str | None:
            values = meta.meta_props.get(key, [])
            return values[0] if len(values) == 1 else None

        if prop("og:url") != expected_url:
            issues.append(f"{page}: og:url mismatch")
        if prop("og:locale") != locale["ogLocale"]:
            issues.append(f"{page}: og:locale mismatch")
        if route in ENGLISH_ONLY_ROUTES:
            expected_alternates = set()
        else:
            expected_alternates = {
                entry["ogLocale"]
                for entry in LOCALES
                if entry["code"] != locale["code"]
            }
        alternates = meta.meta_props.get("og:locale:alternate", [])
        if set(alternates) != expected_alternates or len(alternates) != len(
            expected_alternates
        ):
            issues.append(f"{page}: og:locale:alternate mismatch")

        expected_image = _og_image()
        if prop("og:image") != expected_image:
            issues.append(f"{page}: og:image mismatch")
        if prop("og:image:secure_url") != expected_image:
            issues.append(f"{page}: og:image:secure_url mismatch")
        if prop("og:image:type") != "image/png":
            issues.append(f"{page}: og:image:type mismatch")
        if prop("og:image:width") != str(OG_WIDTH):
            issues.append(f"{page}: og:image:width mismatch")
        if prop("og:image:height") != str(OG_HEIGHT):
            issues.append(f"{page}: og:image:height mismatch")
        if prop("twitter:card") != "summary_large_image":
            issues.append(f"{page}: twitter:card mismatch")
        for og_key, tw_key in (
            ("og:title", "twitter:title"),
            ("og:description", "twitter:description"),
            ("og:image", "twitter:image"),
            ("og:image:alt", "twitter:image:alt"),
        ):
            if prop(og_key) != prop(tw_key):
                issues.append(f"{page}: {tw_key} does not match {og_key}")

        if len(meta.jsonld_chunks) != 1:
            issues.append(
                f"{page}: expected one JSON-LD block, found {len(meta.jsonld_chunks)}"
            )
        else:
            try:
                data = json.loads(meta.jsonld_chunks[0])
            except json.JSONDecodeError as exc:
                issues.append(f"{page}: invalid JSON-LD: {exc}")
            else:
                graph = data.get("@graph")
                if data.get("@context") != "https://schema.org" or not isinstance(
                    graph, list
                ):
                    issues.append(f"{page}: JSON-LD is not a schema.org @graph")
                else:
                    types = {
                        node.get("@type")
                        for node in graph
                        if isinstance(node, dict) and node.get("@type")
                    }
                    for expected_type in ("Organization", "WebSite", "WebPage"):
                        if expected_type not in types:
                            issues.append(f"{page}: JSON-LD missing {expected_type}")
                    if route != "" and "BreadcrumbList" not in types:
                        issues.append(f"{page}: JSON-LD missing BreadcrumbList")
                    if route in PRODUCTS and "SoftwareApplication" not in types:
                        issues.append(
                            f"{page}: JSON-LD missing SoftwareApplication"
                        )
                    if route in ARTICLE_ROUTES and "TechArticle" not in types:
                        issues.append(f"{page}: JSON-LD missing TechArticle")
                    if "FAQPage" in types or "HowTo" in types:
                        issues.append(f"{page}: forbidden JSON-LD type")
                    page_node = next(
                        (
                            node
                            for node in graph
                            if isinstance(node, dict) and node.get("@type") == "WebPage"
                        ),
                        None,
                    )
                    if (
                        not page_node
                        or page_node.get("url") != expected_url
                        or page_node.get("inLanguage") != locale["htmlLang"]
                    ):
                        issues.append(f"{page}: WebPage URL/language mismatch")

        if route in ("", "workbench"):
            if not any("shell-1600.avif" in value for value in meta.srcsets):
                issues.append(f"{page}: missing AVIF hero srcset")
            if not any("shell-1280.avif" in value for value in meta.links):
                issues.append(f"{page}: missing AVIF hero preload")

    return issues


def check_dates(routes: dict[str, Path]) -> None:
    missing = sorted(set(routes) - set(CONTENT_DATES))
    extra = sorted(set(CONTENT_DATES) - set(routes))
    issues = []
    if missing:
        issues.append("CONTENT_DATES missing: " + ", ".join(missing))
    if extra:
        issues.append("CONTENT_DATES unused: " + ", ".join(extra))
    for route in sorted(ARTICLE_ROUTES):
        if route not in ARTICLE_PUBLISHED:
            issues.append(f"ARTICLE_PUBLISHED missing: {route}")
    if issues:
        raise SystemExit("Content date check failed:\n- " + "\n- ".join(issues))


def check_sources() -> None:
    issues: list[str] = []
    for path in sorted(PUBLIC.rglob("*.html")):
        rel = path.relative_to(PUBLIC)
        text = path.read_text("utf-8")
        rel_route = rel.parent.as_posix()
        rel_route = "" if rel_route == "." else rel_route
        required_regions = list(REGIONS)
        if rel_route in ARTICLE_ROUTES:
            required_regions.append("article-meta")
        for region in required_regions:
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
            if local.startswith("/"):
                resolved = (PUBLIC / local.lstrip("/")).resolve()
            else:
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
    issues += i18n.validate(
        stored, catalogs, ignore_routes=ENGLISH_ONLY_ROUTES
    )
    if issues:
        raise SystemExit("Translation check failed:\n- " + "\n- ".join(issues))
    for warning in check_meta_lengths(catalogs):
        print(f"warning: {warning}")


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
    issues += i18n.validate(
        english, catalogs, ignore_routes=ENGLISH_ONLY_ROUTES
    )
    if issues:
        raise SystemExit("Build stopped:\n- " + "\n- ".join(issues))
    for warning in check_meta_lengths(catalogs):
        print(f"warning: {warning}")
    check_locales()
    check_social_assets()
    check_dates(routes)

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
        if src.suffix in (".txt", ".json"):
            dest.write_text(
                src.read_text("utf-8").replace("${site_origin}", SITE_ORIGIN),
                "utf-8",
            )
        else:
            shutil.copy2(src, dest)

    for locale in LOCALES:
        catalog = catalogs[locale["code"]]
        for route, src_path in routes.items():
            if locale["code"] != "en" and route in ENGLISH_ONLY_ROUTES:
                continue
            html = render_site_page(src_path.read_text("utf-8"), route, locale, catalog)
            dest = OUT / ("" if locale["code"] == "en" else locale["code"]) / route
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "index.html").write_text(html, "utf-8")

    write_sitemap(routes)
    issues = output_links_ok() + social_meta_ok()
    if issues:
        raise SystemExit("Built-site link check failed:\n- " + "\n- ".join(issues))
    print(f"Built {OUT.relative_to(ROOT)} ({len(LOCALES)} locales, {len(routes)} routes)")


def write_sitemap(routes: dict[str, Path]) -> None:
    entries: list[str] = []
    for route in sorted(routes):
        lastmod = CONTENT_DATES[route]
        if route in ENGLISH_ONLY_ROUTES:
            entries.append(
                f"  <url>\n"
                f"    <loc>{absolute_url(ENGLISH, route)}</loc>\n"
                f"    <lastmod>{lastmod}</lastmod>\n"
                f"  </url>"
            )
            continue
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
                f"    <lastmod>{lastmod}</lastmod>\n"
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
    """Read metadata, canonical/srcset targets and JSON-LD."""

    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.in_jsonld = False
        self.title = ""
        self.description = ""
        self.links: list[str] = []
        self.meta_props: dict[str, list[str]] = {}
        self.canonicals: list[str] = []
        self.srcsets: list[str] = []
        self.jsonld_chunks: list[str] = []
        self._jsonld = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key:
                self.meta_props.setdefault(key, []).append(a.get("content") or "")
            if key == "description":
                self.description = a.get("content") or ""
        if tag == "link":
            rel = (a.get("rel") or "").lower()
            if "canonical" in rel and a.get("href"):
                self.canonicals.append(a["href"])
            if "preload" in rel and a.get("imagesrcset"):
                self.srcsets.append(a["imagesrcset"])
        if tag in ("img", "source"):
            for attr in ("srcset", "imagesrcset"):
                value = a.get(attr)
                if value:
                    self.srcsets.append(value)
        if tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self.in_jsonld = True
            self._jsonld = ""
        for attr in ("href", "src"):
            value = a.get(attr)
            if value:
                self.links.append(value)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.in_jsonld:
            self.jsonld_chunks.append(self._jsonld)
            self.in_jsonld = False

    def handle_data(self, data):
        if self.in_jsonld:
            self._jsonld += data
        elif self.in_title:
            self.title += data


def check() -> None:
    check_locales()
    check_sources()
    check_catalogs()
    check_social_assets()
    check_dates(source_routes())
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
