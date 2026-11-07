# Catalogue review A7–A8

Approved scope: restore the 30-tour catalogue, retain the compatibility tool through
the common search, and match Karakol and Song-Kol across Latin, Russian and Kyrgyz
spellings. Deployment was outside the initial A7–A8 change. The subsequent
user request adds local A9 preparation only; all server access is prohibited.

1. Add database regression tests with 31 active tours plus inactive/demo rows;
   both catalogue entry points must return the same first 30 active public tours.
2. Add bidirectional destination tests for titles, descriptions and countries,
   including mixed case, spaces and hyphens. Run them before implementation.
3. Make `list_active_tours` delegate to `search_tours`, raise its bound to 30,
   and share alias patterns between Python and PostgreSQL normalization.
4. Run the regression tests, isolated ML suite, full offline suite and lint.
   Update ML documentation with the supported spellings and verification limits.
