# 03 — Move hardcoded scraper settings to site config

**What to build:** Two scraper behaviours are hardcoded in Python and require source edits to change for any site. First, the set of sites that use a dot as decimal separator lives as a Python literal in `price_parser`; adding a new Swedish or dot-decimal site means touching code. Replace it with a `"decimal_separator": "dot"` field read from the site config. Second, the offset pagination step is hardcoded to 60; if a site uses a different page size the config cannot express it. Add a `page_size` key to the pagination block and use it in the paginator, defaulting to 60 for backwards compatibility. Update all existing configs that are affected to carry the explicit field so the behaviour is documented in the config rather than implied by the code.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `price_parser` reads `decimal_separator` from the site config instead of checking a hardcoded set
- [x] All sites previously in the hardcoded set have `"decimal_separator": "dot"` in their config
- [x] Offset paginator reads `page_size` from the pagination block; Karkkainen.com config has `"page_size": 60` explicitly
- [x] Sites without `page_size` continue to use 60 as default (no behaviour change)
- [x] Price parsing results are identical before and after for all existing sites
