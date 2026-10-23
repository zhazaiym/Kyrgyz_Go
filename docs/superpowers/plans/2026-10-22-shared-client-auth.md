# Shared client authentication

Goal: one customer registration for catalogue details and chat, with public catalogue cards.

Existing chat client and token tables remain in use to preserve registered accounts. Authentication moves to client_auth.py and /auth; old /chat/auth paths remain hidden compatibility aliases backed by exactly the same account and token service. No database migration or second customer table is required.

1. Verify failing access tests for public cards, protected details, nested resources and shared login/logout.
2. Expose shared registration/login/profile/logout. Point chat and catalogue to the same dependency.
3. Separate catalogue card schemas from full detail schemas and protect program/gallery resources.
4. Update existing detail tests to use a customer token; preserve administrative write permissions.
5. Document frontend requirements for a single saved token and registration action on HTTP 401.
6. Run targeted access checks and the full regression suite before completion. No deployment.
