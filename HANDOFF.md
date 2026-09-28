# HANDOFF fixer-67
Done: read RULES.md, REVIEW-67.md, PR69 still OPEN (no merge needed).
Next: apply fixes for 2 SHOULDs + 4 NITs listed in REVIEW-67.md:
- jobs.py facets(): only pop kwarg for status/tier/safety/category, not location
- test: facets "location" with location="rem"
- test_ui_api_integration.py: qa_passed "1" case, closes_from/_to case
- HeaderFilterMenu.tsx: skip "" in options; key draft-reset effect on `open` only (ref for filter)
- routers/jobs.py: Query pattern on found/applied/closes from/to
- urlState.ts: avoid double-encoding (escape only commas)
Open: none yet, in progress.
