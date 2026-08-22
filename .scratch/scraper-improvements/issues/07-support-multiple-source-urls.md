# 07 — Support multiple `source_urls` per site config

**What to build:** Each site config currently has a single `source_url`. To cover all product types on sites that split categories across multiple URLs (ticket 08), the runner needs to support scraping several URLs under one site identity — sharing a single `site_id`, `site_name`, and health record. Add a `source_urls` array field to the config schema. When present, the runner iterates over each URL (applying pagination independently per URL) and merges all results into the same site's listings and price readings. A config with only `source_url` (singular) continues to work unchanged. The sleep between pages should also apply between URLs to avoid hammering the same host.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] A config with `"source_urls": ["url1", "url2"]` scrapes both URLs under one `site_id`
- [x] Currency detection, pagination, and health tracking work correctly per URL
- [x] A config with only the existing `source_url` field is unaffected
- [x] Duplicate listings (same `raw_name` appearing on two category pages) are handled by the existing upsert logic without creating duplicates
- [x] Inter-URL sleep is applied (same range as inter-page sleep)
