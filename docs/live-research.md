# Model, search and local instructions

Export configuration variables yourself; the app does not auto-load `.env` or discover credentials.

```bash
export AGENT_MODEL_BASE_URL=https://your-compatible-provider.example/v1
export AGENT_MODEL_NAME=your-model-name
export AGENT_MODEL_API_KEY=your-key
```

Use the endpoint and supported generation settings for your chosen provider. Mission `max_steps` accepts4–30, and `deadline_seconds` accepts10–600. Streaming has separate idle and total budgets; failures preserve completed steps for explicit resume. The provider may still reject or time out.

For the supported MiniMax public-search adapter, set `AGENT_SEARCH_PROVIDER=minimax` and `AGENT_SEARCH_API_KEY`. A mission must explicitly list `search_queries`; only those queries go to search. Company background, selected evidence and related task history go to the configured model. Registered sources use the public HTTPS allowlist. Public fetches reject private IPs and recheck redirect hosts.

## Operator-owned instructions

Optionally set `AGENT_INSTRUCTIONS_FILE` to a UTF-8 file outside the repository, up to24KB. Its contents supplement generic product instructions; the host still enforces tools, scope and budgets. The file is not loaded automatically or bundled. Instructions go to the configured model and persist in private task checkpoints; do not use a shared workspace for separate customers. Resuming a task reuses its saved instructions, so start a new mission to use a changed instruction file.

## Data and exports

The bundled World Bank observations work offline. For current events, explicitly register permitted sources or public queries. Imported evidence and exports are operator-managed; only share data you may redistribute. Runtime files should stay under the private workspace. No automatic GitHub upload or external messaging exists.

Project memory, bounded context, document skills, run controls and usage receipts: [shared kernel guide](kernel.md).
