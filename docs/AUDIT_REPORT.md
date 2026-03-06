# Production Audit Report (Security + Reliability)

## Scope inventory
- Web UI: `templates/storefront.html`, `static/js/store.js`, `static/js/core.js`
- API (store + admin): `store_routes.py`, `web.py`
- Bot process: `main.py`, `handlers.py`, `keyboards.py`
- Data layer: `database.py`
- Deploy/runtime entrypoint: `web.py`

## Threat model (STRIDE + OWASP)
| Threat | Attack path | Impact | Existing control | Fix in this PR |
|---|---|---|---|---|
| Spoofing/Auth state drift | Frontend trusts stale localStorage | Logged-in users appear guest or vice versa | `/api/store/me` exists | Session bootstrap on modal open + page load and strict auth/guest guard |
| Tampering (admin bulk returns input) | malformed IDs split path | Failed operational recovery | Admin auth check | robust parser using regex separators |
| Repudiation / duplicate updates | repeated transaction IDs | double-processing risk | txn lock helpers | duplicated txn returns 409 in manage_balance |
| Information Disclosure | reflected HTML status values | potential DOM XSS | limited | escaped status messages in JS |
| DoS / runtime crash | missing helper symbol in manage_balance | endpoint 500 crash | none | runtime callable guard + controlled JSON failure |

## Findings (ordered)
1. **REL-01 (High)**: profile auth drift / overlapping profile guest state due to weak session bootstrap and guard coupling.
2. **BUG-02 (High)**: `/api/return_orders_bulk` parsing missed mixed separators in real admin input.
3. **REL-03 (High)**: `/api/store/manage_balance` could crash on missing helper symbols.
4. **SEC-04 (Medium)**: unsanitized status HTML rendering path in frontend.
5. **OPS-05 (Medium)**: missing mandatory CI gates for syntax/security checks.
