"""Locale catalogs, block extraction and static page rendering.

Every page stays authored in English under `public/`. A build pass scans the
same block elements for every locale and replaces their inner HTML with the
translated value stored in `i18n/<locale>.json`. Keys are content hashes, so a
translation can never silently attach to different source text: when the English
block changes, its hash changes and the missing key is reported.

Code, commands and SVG stay in the page and are never selected. A translator
receives whole block elements, so inline links and emphasis keep their context.
"""

from __future__ import annotations

import hashlib
import html as html_text
import json
import re
from html.parser import HTMLParser
from pathlib import Path

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}
SKIP = {"pre", "code", "script", "style", "svg", "textarea"}
BLOCK = {
    "h1", "h2", "h3", "h4", "p", "li", "summary", "figcaption", "blockquote",
    "td", "th", "dt", "dd",
}
# Blocks that are pure commands or labels with no prose to translate.
SKIP_CLASSES = {"product-command", "code-block"}

EN_UI = {
    "brand.caption": "Agent development environment",
    "nav.main": "Main",
    "nav.workbench": "Workbench",
    "nav.agent": "Agent",
    "nav.guides": "Guides",
    "nav.blog": "Blog",
    "nav.faq": "FAQ",
    "nav.github": "GitHub",
    "theme.toggle": "Toggle color theme",
    "language.label": "Language",
    "social.imageAlt": "iCode Workbench: one workbench for a fleet of CLI agents",
    "copy.label": "Copy",
    "copy.copied": "Copied",
    "copy.failed": "Copy failed",
    "demo.title": "icode-agent — example session",
    "demo.replay": "Replay",
    "demo.you": "You:",
    "demo.prompt": "Fix the failing tests in this repository.",
    "demo.noteRead": "read 42 lines",
    "demo.noteFail": "observes the failure",
    "demo.noteEdit": "repairs the code",
    "demo.notePass": "verifies: all tests pass",
    "demo.answer": "Fixed add() — it summed the wrong operands. All tests pass.",
    "footer.tagline": "iCode · Tools for people who build software with agents",
    "footer.workbench": "iCode Workbench",
    "footer.agent": "iCode Agent",
    "footer.getStarted": "Get started",
    "footer.guides": "Guides",
    "footer.blog": "Blog",
    "footer.faq": "FAQ",
    "footer.about": "About",
    "footer.github": "GitHub",
    "footer.copy": "© {year} iCode. All rights reserved.",
    "footer.authoritative": "English is the authoritative version of this page.",
}


def page_key(route: str) -> str:
    return "home" if route == "" else route


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def key_for(value: str) -> str:
    return hashlib.sha1(normalize(value).encode("utf-8")).hexdigest()[:12]


def has_letters(inner: str) -> bool:
    return re.search(r"[A-Za-z]", re.sub(r"<[^>]+>", " ", inner)) is not None


def classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    for name, value in attrs:
        if name == "class" and value:
            return set(value.split())
    return set()


def is_block(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    names = classes(attrs)
    if names & SKIP_CLASSES:
        return False
    if tag in BLOCK:
        return True
    if tag == "a" and (names & {"button", "more"}):
        return True
    if tag == "span" and "tag" in names:
        return True
    if tag == "button" and "copy-button" in names:
        return True
    if tag == "button" and "data-demo-replay" in dict(attrs):
        return True
    return False


class _Scanner(HTMLParser):
    """Collect outermost translatable block ranges and image alt values."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.line_starts = [0]
        for line in source.splitlines(keepends=True):
            self.line_starts.append(self.line_starts[-1] + len(line))
        self.blocks: list[dict] = []
        self.alts: dict[str, dict] = {}
        self.stack: list[tuple[str, dict | None, bool]] = []
        self.skip_depth = 0
        self.selected_depth = 0

    def abs_pos(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            raw = self.get_starttag_text() or ""
            match = re.search(r'\balt="([^"]*)"', raw)
            if match and match.group(1).strip():
                value = match.group(1)
                self.alts[key_for(value)] = {
                    "src": dict(attrs).get("src") or "",
                    "en": html_text.unescape(value),
                }
            return
        if tag in VOID:
            return
        if tag in SKIP:
            self.stack.append((tag, None, True))
            self.skip_depth += 1
            return
        if self.skip_depth > 0:
            self.stack.append((tag, None, False))
            return
        if self.selected_depth > 0:
            self.stack.append((tag, None, False))
            return
        if is_block(tag, attrs):
            raw = self.get_starttag_text() or ""
            record = {
                "tag": tag,
                "start": self.abs_pos() + len(raw),
                "end": None,
            }
            self.stack.append((tag, record, False))
            self.selected_depth += 1
            return
        self.stack.append((tag, None, False))

    def handle_startendtag(self, tag, attrs):
        if tag == "img":
            raw = self.get_starttag_text() or ""
            match = re.search(r'\balt="([^"]*)"', raw)
            if match and match.group(1).strip():
                value = match.group(1)
                self.alts[key_for(value)] = {
                    "src": dict(attrs).get("src") or "",
                    "en": html_text.unescape(value),
                }

    def handle_endtag(self, tag):
        end = self.abs_pos()
        while self.stack:
            open_tag, record, skip = self.stack.pop()
            if skip:
                self.skip_depth -= 1
            if record is not None:
                record["end"] = end
                inner = self.source[record["start"]:end]
                if has_letters(inner):
                    record["html"] = inner
                    self.blocks.append(record)
                self.selected_depth -= 1
            if open_tag == tag:
                break


def scan(source: str) -> _Scanner:
    scanner = _Scanner(source)
    scanner.feed(source)
    scanner.close()
    return scanner


def extract_page(source: str) -> dict:
    scanner = scan(source)
    blocks: dict[str, str] = {}
    for block in scanner.blocks:
        blocks[key_for(block["html"])] = normalize(block["html"])
    title = re.search(r"<title>(.*?)</title>", source, re.S)
    description = re.search(
        r'<meta\s+name="description"\s+content="(.*?)"', source, re.S
    )
    return {
        "meta": {
            "title": html_text.unescape(normalize(title.group(1))) if title else "",
            "description": html_text.unescape(description.group(1)) if description else "",
        },
        "blocks": blocks,
        "alts": {key: value["en"] for key, value in scanner.alts.items()},
    }


def extract_site(public: Path, routes: dict[str, Path]) -> dict:
    pages: dict[str, dict] = {}
    for route, path in routes.items():
        pages[page_key(route)] = extract_page(path.read_text("utf-8"))
    return {"locale": "en", "ui": EN_UI, "pages": pages}


def load_catalog(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _replace_ranges(source: str, ranges: list[tuple[int, int, str]]) -> str:
    for start, end, value in sorted(ranges, key=lambda item: item[0], reverse=True):
        source = source[:start] + value + source[end:]
    return source


def _escape_attr(value: str) -> str:
    return html_text.escape(value, quote=True)


def render_page(
    source: str,
    route: str,
    locale: dict,
    catalog: dict,
    ui: dict,
    *,
    href,
    language_menu: str,
    head_extra: str,
    year: str,
    inject_regions,
) -> str:
    page_key_value = page_key(route)
    page = catalog["pages"].get(page_key_value)
    if page is None:
        raise SystemExit(
            f"i18n/{catalog.get('locale', '?')}: missing page {page_key_value}"
        )
    scanner = scan(source)
    ranges: list[tuple[int, int, str]] = []
    for block in scanner.blocks:
        key = key_for(block["html"])
        value = page["blocks"].get(key)
        if value is None:
            raise SystemExit(
                f"i18n/{catalog.get('locale', '?')}: missing block {key} on {page_key_value}"
            )
        ranges.append((block["start"], block["end"], value))
    out = _replace_ranges(source, ranges)

    meta = page["meta"]
    out = re.sub(
        r"<title>.*?</title>",
        f"<title>{html_text.escape(meta['title'])}</title>",
        out,
        count=1,
        flags=re.S,
    )
    out = re.sub(
        r'(<meta\s+name="description"\s+content=").*?(")',
        lambda match: match.group(1) + _escape_attr(meta["description"]) + match.group(2),
        out,
        count=1,
        flags=re.S,
    )

    def replace_alt(match: re.Match[str]) -> str:
        value = match.group(2)
        translated = page["alts"].get(key_for(value)) if value.strip() else None
        if translated is None:
            return match.group(0)
        return match.group(1) + _escape_attr(translated) + match.group(3)

    out = re.sub(r'(<img\b[^>]*\balt=")([^"]*)(")', replace_alt, out)

    if locale["code"] != "en":
        out = re.sub(
            r'((?:href|src)=")(?:\.\./|\./)*assets/',
            r'\1/assets/',
            out,
        )
    out = re.sub(
        r'(<html\b[^>]*\blang=")[^"]*(")',
        lambda match: match.group(1) + locale["htmlLang"] + match.group(2),
        out,
        count=1,
    )
    out = re.sub(
        r"<html\b([^>]*)>",
        lambda match: (
            "<html"
            + match.group(1)
            + f' data-copy-label="{_escape_attr(ui["copy.label"])}"'
            + f' data-copy-copied="{_escape_attr(ui["copy.copied"])}"'
            + f' data-copy-failed="{_escape_attr(ui["copy.failed"])}"'
            + ">"
        ),
        out,
        count=1,
    )
    out = inject_regions(out, locale, route, ui, href, language_menu)
    demo = {
        key.removeprefix("demo."): value
        for key, value in ui.items()
        if key.startswith("demo.")
    }
    demo_script = (
        '<script id="demo-i18n" type="application/json">'
        + json.dumps(demo, ensure_ascii=False, separators=(",", ":"))
        + "</script>"
    )
    out = out.replace("</head>", head_extra + "\n" + demo_script + "\n</head>", 1)
    out = out.replace("{{year}}", year)
    return out


class _Signature(HTMLParser):
    """Tags and link targets that a translation must not change."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.classes: list[str] = []
        self.extras: list[tuple[tuple[str, str], ...]] = []
        self.links: list[tuple[str, str]] = []
        self.code_text: list[str] = []
        self.code_depth = 0

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attributes = dict(attrs)
        self.classes.append(attributes.get("class") or "")
        self.extras.append(
            tuple(
                sorted(
                    (name, value or "")
                    for name, value in attributes.items()
                    if name == "id" or name.startswith("data-")
                )
            )
        )
        if tag in ("code", "pre"):
            self.code_depth += 1
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.links.append((name, value))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in ("code", "pre") and self.code_depth > 0:
            self.code_depth -= 1

    def handle_data(self, data):
        if self.code_depth > 0:
            self.code_text.append(data)


def signature(
    value: str,
) -> tuple[list[str], list[str], list[tuple[tuple[str, str], ...]], list[tuple[str, str]], list[str]]:
    parser = _Signature()
    parser.feed(value)
    return parser.tags, parser.classes, parser.extras, parser.links, parser.code_text


def validate(english: dict, catalogs: dict[str, dict]) -> list[str]:
    issues: list[str] = []
    routes = set(english["pages"])
    for code, catalog in catalogs.items():
        if code == "en":
            continue
        if set(catalog.get("pages", {})) != routes:
            missing = routes - set(catalog.get("pages", {}))
            extra = set(catalog.get("pages", {})) - routes
            if missing:
                issues.append(f"i18n/{code}: missing pages {sorted(missing)}")
            if extra:
                issues.append(f"i18n/{code}: unknown pages {sorted(extra)}")
        for route in sorted(routes & set(catalog.get("pages", {}))):
            source_page = english["pages"][route]
            page = catalog["pages"][route]
            for field in ("meta", "blocks", "alts"):
                missing = set(source_page[field]) - set(page.get(field, {}))
                extra = set(page.get(field, {})) - set(source_page[field])
                if missing:
                    issues.append(f"i18n/{code}: {route} missing {field} {sorted(missing)}")
                if extra:
                    issues.append(f"i18n/{code}: {route} unknown {field} {sorted(extra)}")
            for field in ("title", "description"):
                if not str(page.get("meta", {}).get(field, "")).strip():
                    issues.append(f"i18n/{code}: {route} empty meta.{field}")
                if "<" in str(page.get("meta", {}).get(field, "")):
                    issues.append(f"i18n/{code}: {route} meta.{field} contains markup")
            for key, translated in page.get("blocks", {}).items():
                if not str(translated).strip():
                    issues.append(f"i18n/{code}: {route} empty block {key}")
                    continue
                if signature(source_page["blocks"][key]) != signature(str(translated)):
                    issues.append(f"i18n/{code}: {route} block {key} changed markup")
            for key in page.get("alts", {}):
                if not str(page["alts"][key]).strip():
                    issues.append(f"i18n/{code}: {route} empty alt {key}")
                if "<" in str(page["alts"][key]):
                    issues.append(f"i18n/{code}: {route} alt {key} contains markup")
        missing_ui = set(english["ui"]) - set(catalog.get("ui", {}))
        extra_ui = set(catalog.get("ui", {})) - set(english["ui"])
        if missing_ui:
            issues.append(f"i18n/{code}: missing ui {sorted(missing_ui)}")
        if extra_ui:
            issues.append(f"i18n/{code}: unknown ui {sorted(extra_ui)}")
        if "{year}" not in str(catalog.get("ui", {}).get("footer.copy", "")):
            issues.append(f"i18n/{code}: ui.footer.copy lost the {{year}} placeholder")
    return issues
