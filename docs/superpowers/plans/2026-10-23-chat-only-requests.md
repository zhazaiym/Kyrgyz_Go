# Chat-only requests implementation plan

**Approved design:** Only confirmed chat conversations create new travel requests. Remove the general requests view from the admin navigation; keep historical rows intact. Retire standalone public submission endpoints with HTTP 410 and instructions to open a chat. Keep existing protected management endpoints for historical data.

**Steps:**
- Add regression tests for retired submission routes without database writes, absence of the old admin view and manager acknowledgement after chat confirmation. Run the tests before implementation.
- Remove registration of the old admin view, replace standalone creation handlers with retirement responses and update localized confirmation acknowledgements.
- Document a frontend-free Postman WebSocket walkthrough and run targeted tests followed by the full test suite.

**Constraints:** No removal of historical records or database tables. No frontend or server deployment in this task. Keep explicit confirmation, no premature submissions and duplicate protection unchanged.
