# Matching configuration

`matching.json` is the reviewed vocabulary and threshold configuration used by the deterministic matcher.

`catalogue_states.json` is the runtime source of truth for allowed and blocked family confidence tokens. Catalogue validation requires its combined values to exactly match the JSON Schema enum.

Before adding a synonym:

1. Add a real anonymised enquiry that demonstrates the need to `tests/test_bot_engine.py`.
2. Check that the replacement is specific enough not to change unrelated meanings.
3. Add at least one negative/edge case when the phrase is ambiguous.
4. Run `pytest -q` and review the top three candidates, not only the winner.

Tune `fuzzy_word_threshold` and `no_reliable_match_score` only against a labelled enquiry set. Lower values increase recall but also increase false recommendations. `singularisation_exceptions` protects words whose trailing `s` is not a simple plural.
