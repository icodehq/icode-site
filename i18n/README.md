# Site translations

The site is a static build with one authored English page tree and one JSON
catalog per locale. English stays at the site root; the other catalogs are
emitted under their language code (`/zh-CN/`, `/ja/`, …).

## Files

- `i18n/locales.json` — language codes, native labels, and `<html lang>` values.
- `i18n/en.json` — English source catalog, generated from `public/`:
  `python3 scripts/site.py extract`.
- `i18n/<code>.json` — translated catalog with the same shape.

Each page object has:

```json
{
  "meta": { "title": "…", "description": "…" },
  "blocks": { "<content hash>": "<translated HTML>" },
  "alts": { "<content hash>": "<translated alt text>" }
}
```

Block keys are content hashes of the English source. If an English block
changes, its key changes and the build fails until the catalog is updated. This
is deliberate: a stale translation must never silently attach to new copy.
`ui` holds the shared header, footer, language menu, and copy-button strings.

## Translation rules

- Translate the text, not the markup. Preserve every HTML tag, attribute,
  `href`, `src`, entity, and URL exactly.
- Do not translate product names, vendor names, platform names, licenses,
  commands, code identifiers, file paths, flags, or anything inside `<code>`.
  Examples: iCode, iCode Workbench, iCode Agent, Mira, Claude Code, Codex,
  OpenCode, GitHub, Node.js, npm, pnpm, AGPL-3.0-only, Apache-2.0, OpenAI,
  Anthropic, Linux, Windows, macOS, WSL2/WSLg, Monaco, SQLite, JSON, CI, API.
- Keep placeholders such as `{year}` exactly as written.
- Use the terminology already used by the Workbench app and localized READMEs:
  `/mnt/d/Development/OrcaProjects/iCode/src/shared/i18n/catalogs/<code>.ts`
  and `/mnt/d/Development/OrcaProjects/iCode/README.<code>.md`.
- Marketing copy should read naturally in the target language, not word for
  word. Keep it concise.
- The English page is authoritative. Localized pages carry a translated note
  saying so.

## Workflow

```sh
python3 scripts/site.py extract       # refresh i18n/en.json after copy changes
python3 scripts/site.py check         # source, catalog and coverage checks
python3 scripts/site.py build         # render every locale into _site/
python3 scripts/site.py deploy-check  # check + build
python3 scripts/site.py serve         # preview http://127.0.0.1:4173/
```

When an English block changes, `check` reports the missing hash for every
locale. Re-translate that block and keep the rest of the catalog.

## Adding a language

1. Add the code, native label, and `htmlLang` to `i18n/locales.json`.
2. Create `i18n/<code>.json` from `i18n/en.json` with translated values.
3. Run `deploy-check`. The header language menu, hreflang links, and sitemap
   pick the new locale up automatically.
