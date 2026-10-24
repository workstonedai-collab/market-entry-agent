# Contributor guidance

Keep the runtime standard-library only and independently runnable. Publish only PUBLIC_FILES.json entries. Keep operator-owned instructions, private knowledge, customer documents, credentials, runtime state and archives outside the repository. New examples must use synthetic or attributed public data. Run the public-release checker before packaging. Common files must match the peer manifest. Test actual recovery, scope and saved/exported results. Do not enable external sending or background jobs by default. Use GitHub noreply commit identities.

Keep deployment-specific privacy rules in local/CI `PUBLIC_RELEASE_DENY_PATTERNS` (a JSON array of regular expressions), not in published source.

部署专用的隐私匹配规则通过本地或 CI 的 `PUBLIC_RELEASE_DENY_PATTERNS` 配置（正则表达式的 JSON 数组），不要把具体部署名称写入公开源码。
