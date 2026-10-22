---
name: market-entry-agent
description: Run a bounded market entry agent mission and inspect saved research, evidence and tool steps.
---

Use the installed `market-entry-agent` CLI. Read the repository README and the user's supplied mission first. Use a dedicated private workspace and only deliberately imported or explicitly configured public sources. Run `demo` for a synthetic walkthrough; use `run mission.json --engine model` only with an explicitly configured provider. Reopen results with `show RUN_ID` and export with `export RUN_ID --output report.md`. For public search, use only user-approved `search_queries`; never derive a public query from private company context. Register permitted feeds/pages with `sources`; retrieve them with `fetch` / `fetch-page`. Read `docs/live-research.md` and `docs/hermes.md` before real-source use. Failed tasks may be resumed with `resume RUN_ID`. Never claim the deterministic demo is model research or current intelligence. Do not start a worker, share private evidence or send external notifications without the user's corresponding instruction.

Read `docs/kernel.md` for explicit project IDs, private operator facts, document skills and call receipts. Use the same project ID only for authorized related research; different customers still require separate workspaces. Never treat previous analysis as independent source evidence. `pause-run` and `cancel` affect research runs; `pause` still affects schedules.
