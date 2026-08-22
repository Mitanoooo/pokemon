# 08 — Add missing category URLs to site configs

**What to build:** Using the findings from ticket 06 (the coverage audit), update each site config to include all category URLs needed for full sealed-product coverage. Where a site splits product types across multiple paths, use the `source_urls` array added in ticket 07. Verify each new URL produces readings in a test scrape before marking the ticket done.

**Blocked by:** 06 (coverage audit), 07 (multi-URL runner support).

**Status:** done

- [ ] Every site identified in the audit as having coverage gaps has its config updated with the missing category URLs
- [ ] A test scrape produces readings for previously-missing product types (ETBs, tins, blisters, collections) on at least the highest-gap sites
- [ ] No existing readings or listings are duplicated or overwritten by the new URLs
- [ ] Sites confirmed as complete in the audit are unchanged
