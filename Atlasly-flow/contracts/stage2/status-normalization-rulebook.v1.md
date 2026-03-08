# Stage 2 Status Normalization Rulebook v1

## Scope
- Connector status normalization priority and confidence policy.
- Invalid-transition handling policy.
- Reconciliation drift classification taxonomy.

## Normalization order
1. Connector/AHJ exact match rule (`match_type=exact`) -> default confidence `0.99`.
2. Connector/AHJ regex rule (`match_type=regex`) -> default confidence `0.95`.
3. Lexical fallback (`match_type=lexical`) -> confidence `0.75`.
4. Conflicting lexical matches -> confidence penalty `-0.20`.

## Canonical status set
- `submitted`
- `in_review`
- `corrections_required`
- `approved`
- `issued`
- `expired`

## Allowed transitions
- `submitted -> in_review|corrections_required|approved|issued`
- `in_review -> corrections_required|approved|issued`
- `corrections_required -> submitted|in_review|approved`
- `approved -> issued|expired`
- `issued -> expired`
- `expired` is terminal for auto-transition.

## Invalid transition policy
- Persist raw observation in `permit_status_events`.
- Do not mutate projected permit status.
- Create review queue item in `status_transition_reviews` with `resolution_state=open`.

## Drift classification
- `mapping_drift`: projected status differs and ruleset version changed.
- `source_drift`: projected status differs and source payload hash changed with same ruleset version.
- `timeline_gap`: projected status differs without ruleset or payload change.
