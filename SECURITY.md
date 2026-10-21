# Security

This alpha is for a trusted single operator. Separate customer workspaces and use an authenticated TLS reverse proxy for remote access. The local API rejects cross-origin writes and requires a token for non-loopback binding. Public feed fetching pins a validated public IP and rechecks redirect hosts. The model endpoint is explicitly configured by the operator and may be local. Source claims are untrusted data. There is no shell execution, credential discovery or external message sending.

Report vulnerabilities through a private GitHub security advisory if enabled, or a minimal issue asking for a private contact; do not post secrets or exploit details publicly.
