# Hermes 接入 / Hermes integration

Use a dedicated research profile. This product executes its own bounded tools; Hermes should supply model responses without nested terminal, browser, filesystem or messaging tools. Existing personal profiles are not modified.

## 独立配置 / Dedicated configuration

Create a separate profile using your installed Hermes profile workflow, or a separate root with the **`profiles/research`** layout and `HERMES_HOME` pointing to that profile directory. On macOS keep this path short: Unix sockets have a path-length limit. An arbitrary new root may still be treated as the default profile by the service-name guard. Verify profile and service identity before starting; do not force past a conflict with an active personal gateway.

Example `config.yaml` in the dedicated profile:

```yaml
model:
  default: MiniMax-M3.1-Flash
  provider: minimax
  base_url: https://api.minimax.io/anthropic
platform_toolsets:
  api_server: []
mcp_servers: {}
agent:
  max_turns: 3
```

Set the selected provider credential yourself. For this MiniMax example that is `MINIMAX_API_KEY`. Set a newly generated random `API_SERVER_KEY` (at least 16 characters), `API_SERVER_HOST=127.0.0.1`, and an unused `API_SERVER_PORT` such as 8642 in that process. Start **`hermes gateway run`** in the foreground with the dedicated `HERMES_HOME`. `API_SERVER_ENABLED` alone does not enable a usable listener in the installed version tested here.

Do not copy a personal `.env`, private memory or unrestricted tool configuration into the profile. Set an appropriate minimal persona for this JSON-action service. `platform_toolsets.api_server: []` is an explicit empty list; check `/v1/toolsets` to confirm every toolset is disabled. A capability endpoint's phrase `tool_execution: server` describes the runtime architecture, not permission to use tools.

## 连接产品 / Connect the product

```bash
export AGENT_MODEL_BASE_URL=http://127.0.0.1:8642/v1
export AGENT_MODEL_NAME=research
export AGENT_MODEL_API_KEY=your-dedicated-api-server-key
export AGENT_MODEL_STREAM=true
export AGENT_MODEL_IDLE_SECONDS=180
python scripts/check_hermes.py
market-entry-agent run examples/mission.json --engine model
```

Use the model/profile alias advertised by `/v1/models`, the actual listener port, and the dedicated API key. The product sends full conversation context on each stateless chat request; it does not depend on provider-native function calling or reuse a personal Hermes session. The model selects one JSON action in assistant text; only the product's documented tools execute locally. Incomplete streams and truncated output remain resumable failures.

References: [Hermes Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles), [API Server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server). No provider key or existing private profile is bundled.
