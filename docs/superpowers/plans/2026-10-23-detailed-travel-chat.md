# Detailed travel consultation and booking collection

The latest user request reinstates a minimum of 1000 substantive runtime prompt lines. It supersedes the previous compact-prompt size requirement. The output budget still limits generated answers; it does not reduce the input cost of a longer system prompt.

1. Expand prompts.py without duplicating rules for padding. Keep owner-provided company information and existing database tools.
2. Explain recommendations and selected tours in meaningful detail using actual programme, price, inclusion and exclusion data. Simple factual answers remain concise; no universal 2–5-sentence restriction applies to tour explanations.
3. Ask one or two relevant selection questions at a time. Gather booking contacts only when the client wants to submit a request.
4. Pass the last question and recent dialogue to structured extraction so short answers can be assigned to the correct fields. The latest message supplies changes; prior context only disambiguates.
5. Preserve server validation, complete preview, explicit confirmation, ownership checks, revision invalidation and idempotent admin submission.
6. Raise the default answer allowance to 1536 tokens with a hard ceiling of 4096. Bound extraction to at most 1024 tokens; default remains 512. Preserve retry handling for exhausted output limits.
7. Verify prompt line count/format/uniqueness, contextual extraction, collection flow, token caps and the complete regression suite. Do not deploy this task automatically.
