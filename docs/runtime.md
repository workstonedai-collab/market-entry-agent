# Runtime and recovery

Every tool observation and model context is checkpointed in SQLite. A completed result and local notification are written in one transaction. Repeating `resume RUN_ID` returns the existing result if complete. A running lease blocks concurrent owners; an interrupted process becomes resumable after its configured deadline plus a short lease margin. Saved read-only steps are not repeated.

Failed runs expose a short error class. Provider response bodies and API credentials are not written to logs. A model network failure can be retried with `resume`; fix configuration or wait for quota before doing so. The total step budget is retained across resume. An exhausted budget requires a revised mission/new run. No automatic paid retry loop is enabled.

```bash
market-entry-agent list
market-entry-agent show RUN_ID
market-entry-agent resume RUN_ID
market-entry-agent export RUN_ID --output report.md
```

The recurring worker is an explicit foreground process. Use one intended process supervisor. Due schedules are leased so two workers do not both claim the same due task. The next run is scheduled after the current attempt; failures remain visible as failed runs. Pause a schedule with `pause SCHEDULE_ID`.

Recurring tasks research the current imported evidence; a model may choose to refresh registered feeds. A deterministic demo never makes network requests. Stable evidence and mission identity deduplicate notification entries, while reports retain independent versions. Notifications are local and pending review; `approve` marks one approved but does not send it anywhere. New confirmed watches provide an opt-in Hermes CLI connector with destination binding, private-material consent and durable send receipts; legacy approve still changes local state only. See [continuous research](continuous-research.md).

Project memory, bounded context, document skills, run controls and usage receipts: [shared kernel guide](kernel.md).

Private product workflow, versioned records and public-source replay: [guide](product-workflow.md).
