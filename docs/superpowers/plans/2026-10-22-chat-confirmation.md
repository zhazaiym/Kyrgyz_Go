# Chat confirmation and prompt implementation plan

Goal: expand the existing runtime prompts and expose explicitly confirmed chat requests in their own authenticated admin section.

The existing consultation, collecting, awaiting_confirmation and submitted stages remain authoritative. Complete data produces a server summary. Exact affirmative replies are accepted only while awaiting confirmation; rejection returns to collecting without creating a request. Existing revision checks and idempotent booking links remain in use.

1. Add regression tests for complete-data preview, approval, rejection, corrections, idempotency, and authenticated filtered admin visibility.
2. Replace the broken confirmation constant and implement deterministic acceptance/rejection before calling AI.
3. Add a filtered SQLAdmin view over existing TravelRequest records linked through ChatBookingLink; preserve the general request section.
4. Expand prompts.py with at least 1000 substantive policy lines, maintaining runtime placeholders and extraction schema.
5. Run targeted tests, prompt formatting checks, and relevant regression tests. Document local verification steps. Do not deploy or change chat authentication in this task.
