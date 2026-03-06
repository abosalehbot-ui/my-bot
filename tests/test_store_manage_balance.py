import asyncio

import store_routes


def test_manage_balance_fails_safe_when_helpers_missing(monkeypatch):
    scope = {"type": "http", "method": "POST", "headers": []}
    request = store_routes.Request(scope)

    monkeypatch.setattr(store_routes, "check_auth", lambda _req: True)
    monkeypatch.setitem(store_routes.__dict__, "_sanitize_positive_int", None)

    response = asyncio.run(
        store_routes.store_manage_balance(
            request=request,
            email="test@example.com",
            amount=10,
            action="add",
            currency="EGP",
            transaction_id="",
        )
    )

    assert response.status_code == 500
    assert b"balance validators unavailable" in response.body
