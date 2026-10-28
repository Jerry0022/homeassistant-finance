# Contract: categorisation and open questions

Cache-only; no bank call anywhere. Merchant memory lives in the HA Store
`finance_dashboard_merchants` (merchant keys, categories, owners, booking ledger
ids, counters; never amounts, IBANs or dates).

## Categorisation chain (per booking, derived from the ledger)

1. one-off booking answer (`reach: "booking"`) ->
2. learned merchant (`reach: "merchant"`) ->
3. keyword rules (`const.CATEGORIZATION_RULES` + `categorizer.EXTRA_RULES`) ->
4. positive amount -> `income` ->
5. `other`.

New category ids produced only by keyword rules / answers: `shopping`, `health`,
`leisure` (not in `DEFAULT_CATEGORIES`, so no budget-limit entities exist for
them). The frontend needs labels for these. Any slug `^[a-z][a-z0-9_]{0,31}$`
except `other` is a valid answer category.

A merchant answer may carry an `owner` (`shared` or a person name): it is exposed
on the derived booking as `_owner_override` and replaces the account default in
`home.py` ownership.

## Home payload additions (`GET /api/finance_dashboard/home`, unchanged URL)

- `questions_open` (int, 0..10): merchants asked this calendar week = open "other"
  booked expenses of the cycle, not in a transfer chain, grouped per merchant,
  capped at `10 - answered_this_week`.
- `questions_total` (int): total merchants still waiting (backlog).
- `did_you_know` never reports category `other`.

## `GET /api/finance_dashboard/questions` (admin only, 403 `admin_required`)

Household-cycle view. Response:

```json
{
  "questions": [
    {"id": "the studio", "merchant": "The Studio", "count": 3, "total": 84.5,
     "dates": ["2026-10-21", "2026-10-09"], "booking_ids": ["..."],
     "suggested": ["leisure", "shopping", "food"]}
  ],
  "questions_open": 1, "questions_total": 12,
  "answered_total": 31, "week_answered": 4,
  "points": 1, "points_every": 30
}
```

`id` is the stable merchant key; `total` is the absolute euro sum of the open
bookings; `dates` holds up to 3 newest booking dates; `suggested` is the top 3
categories (most-taught first, padded with defaults).

## `POST /api/finance_dashboard/questions/answer` (admin only)

Body: `{"id": "the studio", "category": "leisure", "reach": "merchant"|"booking", "owner": "Anna"?}`

- `merchant`: writes the memory; all matching bookings (past and future) are
  re-derived from the ledger.
- `booking`: one-off for the currently open bookings of that merchant only.

200: `{"answered_total": 31, "week_answered": 5, "point_awarded": false}`.
Every 30th answered question sets `point_awarded: true` and fires the HA event
`finance_dashboard_points` with `{"user_id": "<answering HA user>", "points": 1}`
(a merchant-wide rule counts once).

400 `{"error": code, "detail"}`: `invalid_body`, `invalid_id`, `invalid_category`,
`invalid_reach`, `invalid_owner` (not `shared` / a known person),
`unknown_question` (booking reach with no open booking), `unavailable`
(demo mode / memory not loaded).
