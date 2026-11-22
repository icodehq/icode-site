# iCode website

Static marketing site for iCode and its two products:

- **iCode Workbench** — the open-source agent development environment for a fleet of CLI agents.
- **iCode Agent** — the terminal coding agent.

Framework-free, by design: authored HTML in `public/`, shared regions injected
from `templates/`, translations in `i18n/`, output generated into `_site/`. No
npm dependency, no bundler, no runtime backend. Deployment is a static directory,
so the same output works on Vercel, Cloudflare Pages, or any static host.

English is served from the site root; the other supported locales are emitted
under their language code (`/zh-CN/`, `/ja/`, …) with localized metadata,
`hreflang` links, a language menu and sitemap entries.

## Layout

```
public/                 authored source
  index.html            home (umbrella hero, products, Mira, principles)
  workbench/            iCode Workbench product page, availability, and build notes
  agent/                iCode Agent product page (context, demo, workflows)
  get-started/          install iCode Agent, model setup, first run
  first-investigation/  a guided first Agent task
  guides/               Agent workflow guides (index + fix-a-failing-test, refactor-a-module, track-down-a-bug, automate-in-ci)
  blog/                 index + "The context window is a budget"
  faq/                  Agent objection-handling Q&A
  about/                company and product overview
  assets/               styles, theme/main/demo JS, logo, Workbench screenshots
templates/              shared header/footer partials
i18n/                   locale list, English source catalog and translations
scripts/site.py         build / check / serve / extract
scripts/i18n.py         block extraction and locale rendering
evidence/               source-of-truth notes backing site claims
_site/                  generated output (gitignored)
vercel.json             Vercel config (framework: null, output: _site)
```

## Content honesty rules

- **No invented numbers.** The site states no token-saving percentage or absolute
  figure, because no benchmark has been run. Add a number only with a matching
  file in `evidence/`.
- **No invented case studies.** There is no showcase page until a real session is
  recorded and published with its transcript and usage.
- **The terminal demo is labelled illustrative.** It shows the tool loop; it is
  not a recorded run.
- **Workbench screenshots are real UI captures.** They show the app, not a mockup.
  Keep their captions tied to what is visible.
- **Workbench is pre-1.0.** Its source is public under AGPL-3.0-only.
  Unsigned installers are published on GitHub Releases; public pages point to
  the Releases page and the build-from-source path, and state the expected
  Windows SmartScreen and macOS Gatekeeper warnings.
- Claims about context mechanics are backed by `evidence/context-management.md`,
  which cites the exact source files.
- Harness counts (44 launchable, 21 managed hooks, 3 native) are backed by
  `evidence/harness-catalog.md`, which cites the catalog and hook registry.
- Product limits are stated in `public/workbench/` and in the Agent FAQ rather
  than hidden.

## Commands

```sh
python3 scripts/site.py extract       # refresh the English catalog from public/
python3 scripts/site.py check         # validate source, links and translations
python3 scripts/site.py build         # render every locale into _site/
python3 scripts/site.py serve         # build if needed, then preview :4173
python3 scripts/site.py deploy-check  # check + build, then ready to deploy
```

Only the Python standard library is required.

The sitemap and `robots.txt` use `https://icodehq.com` by default. On Vercel,
the build uses `VERCEL_PROJECT_PRODUCTION_URL` when it is available. Override the
origin explicitly for another deployment:

```sh
SITE_ORIGIN=https://example.com python3 scripts/site.py build
```

`public/robots.txt` contains `${site_origin}`; the build replaces it with the
configured origin.

## Translations

Every page is rendered in all locales listed in `i18n/locales.json`. The English
catalog is generated from the authored HTML, and block keys are content hashes so
a changed English block cannot silently reuse an old translation. See
[i18n/README.md](i18n/README.md) for the catalog format, translation rules, and
the full workflow.

## Adding a page

1. Add `public/<route>/index.html` with these markers where the shared chrome goes:

   ```html
   <!-- BEGIN:site-header --><!-- END:site-header -->
   ...
   <!-- BEGIN:site-footer --><!-- END:site-footer -->
   ```

2. Add a `<title>` and a `<meta name="description">` (both are checked).
3. Use relative links for pages. Localized builds rewrite shared asset URLs to
   `/assets/...` automatically.
4. Run `python3 scripts/site.py extract`, add the new blocks to every catalog,
   then run `python3 scripts/site.py deploy-check`.

## Deploying to Vercel

Import this directory as a project. Vercel reads `vercel.json`, runs the build,
and serves `_site/`. No framework preset is needed.

## Notes

- `scripts/site.py` is modelled on REA's MIT-licensed website tooling; see
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- The site is proprietary. iCode Workbench is AGPL-3.0-only; iCode Agent is
  Apache-2.0.
