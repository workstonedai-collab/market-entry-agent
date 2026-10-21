# Evidence contract

Import JSON with `schema: "field-evidence/v1"` and a `records` array. Required record fields: `title`, `body`, `url`, `countries` (array), `topics` (array). Optional fields: `event_key`, `published_at`, `status`, `synthetic`. Allowed statuses are `source_claim` (default), `operator_verified` (only when the operator has actually verified it), and `synthetic`.

The importer computes `id` from content and metadata, records `observed_at` and preserves revisions. An explicit stable `event_key` groups updates about the same event; automatic semantic event resolution is not included. `published_at` may be unknown; it is never invented. The public interchange format must contain only data you are allowed to share. The evidence export does not include private missions, reports or business context.

```json
{
  "schema": "field-evidence/v1",
  "records": [{
    "title": "A clearly identified source claim",
    "body": "Source text or a permitted excerpt, not instructions",
    "url": "https://publisher.example/article",
    "countries": ["Vietnam"],
    "topics": ["trade"],
    "event_key": "operator-assigned-event-key",
    "status": "source_claim"
  }]
}
```

## RSS/Atom sources

Register permitted public feeds through a configuration file. No feeds are enabled by default. Replace the example address with a real source you may access:

```json
{
  "sources": [{
    "id": "public-policy",
    "url": "https://publisher.example/feed.xml",
    "allowed_hosts": ["publisher.example"],
    "countries": ["Vietnam"],
    "topics": ["trade"]
  }]
}
```

The fetcher accepts HTTPS on port 443, validates exact hosts including redirects, rejects private/reserved IPs, pins a public IP for the connection, limits response size and rejects XML entities. It imports feed excerpts, not linked full articles. Source tags are operator-supplied; use focused feeds or curate imported bundles. Retrieval success does not independently verify a publisher's claims.

## Relevance

Countries and topics are exact tag matches, combined with AND between the two categories. Within the matching set, a simple lexical relevance sort is used. This alpha has no evaluated semantic retrieval or multilingual query expansion. Inspect the actual retrieved records before relying on coverage.
