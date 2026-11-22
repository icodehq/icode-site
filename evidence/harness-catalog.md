# Harness catalog counts

Source: `icodehq/icode-workbench` at `master` (commit `91631ab`).

- `src/shared/domain/harness-catalog.ts` defines 46 harness entries.
  - `shell` is iCode's terminal entry, not an agent.
  - `claude-agent-teams` is marked `unsupported` (a third-party CLI wrapper
    that cannot be launched from iCode).
  - **44 entries are launchable agents.**
  - `MODEL_HARNESSES` is `['claude', 'codex', 'opencode']` — the three with
    native provider injection and Mira's native conversation.
- `src/shared/domain/managed-hook-providers.ts` lists the **21 managed hook
  providers**:

  `gemini`, `qwen-code`, `cursor`, `copilot`, `grok`, `kimi`, `amp`, `droid`,
  `openclaude`, `qoder`, `qoder-cn`, `codebuddy`, `antigravity`,
  `command-code`, `devin`, `muse`, `zcode`, `kiro`, `dsh`, `jcode`, `hermes`.

- `harness-catalog.ts` sets `HARNESS_CAPABILITIES[id].activity.hook = true`
  for each entry in `MANAGED_HOOK_PROVIDER_IDS`.

Counts used on the site: **44 launchable / 21 managed hooks / 3 native**.
