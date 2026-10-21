# Deploying the alpha

GitHub publication delivers source, release artifacts and CI. It is separate from operating a hosted service.

## Local operator

Install from the repository and run `market-entry-agent demo`, then `market-entry-agent serve`. State defaults to `~/.field-agents/market-entry-agent`. Use an explicit `--workspace` when serving different customers. Start `worker` separately if monitoring is desired.

## Container

```bash
docker build -t market-entry-agent .
docker run --rm market-entry-agent demo
export AGENT_UI_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
docker compose up --build -d
```

The Compose file maps the browser port to host loopback and stores state in a named volume. Non-loopback serving inside the container requires the token. Enter it in the browser's workspace connection form. To import the synthetic demo into this persistent volume, run `docker compose exec app market-entry-agent --workspace /workspace demo`. To enable an explicit continuous worker, run `docker compose --profile monitor up -d`.

Export model environment variables before creating the containers if using model mode. The container does not inherit your laptop's local gateway automatically. Never commit `.env` files or keys. The app reads exported variables; `.env.example` documents the names and the app does not auto-load it.

## Remote operator

Run behind an authenticated TLS reverse proxy. Set `AGENT_UI_ALLOWED_HOSTS` to the exact external hostname(s), pass the Host header consistently, and keep the token in place. Do not use the standard-library server as an unauthenticated public multi-user service. Configure backups for the workspace volume. These recipes are for self-hosting; no hosted domain or SLA is included in v0.2.

## Verification

After deployment, import a known permitted evidence bundle, run a mission, reopen its saved result, then test a failed model request and recovery. For recurring tasks, start the worker and prove a due task completed and appeared in local history. A health response alone does not prove that research or notifications are working.
