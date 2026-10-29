"""Wizard backend: plan prefill, goals, points hand-off, AI budget/key, nicknames.

All figures are invented.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.finance_dashboard import ai_provider as ai
from custom_components.finance_dashboard import plan_prefill as prefill
from custom_components.finance_dashboard import points_target as pts
from custom_components.finance_dashboard import savings_goals as goals
from custom_components.finance_dashboard import setup_wizard as wiz
from custom_components.finance_dashboard.budget_plan import CostPosition

TODAY = date(2026, 10, 29)


def _contract(sid, name, owner, monthly, **kw):
    return {
        "id": sid,
        "creditor": name.lower(),
        "display_name": name,
        "owner": owner,
        "category": "subscriptions",
        "interval": "monthly",
        "monthly_equivalent": monthly,
        "status": "active",
        "contract": {"plan_position_id": None, "stored": {"plan_mode": None}},
        **kw,
    }


# --- notifications default ----------------------------------------------------


def test_wizard_default_notifications_on() -> None:
    assert wiz.default_state()["notifications"]["enabled"] is True


# --- plan prefill --------------------------------------------------------------


def test_prefill_proposes_live_contracts_with_owner_and_monthly_amount() -> None:
    contracts = [
        _contract("s1", "Streamflix", "shared", 12.99),
        _contract("s2", "Gym", "Anna", 29.0),
        _contract("s3", "Old", "Anna", 5.0, status="ended"),
        _contract("s4", "Zero", "Anna", 0.0),
    ]
    out = prefill.propose_positions(contracts, [])
    assert [p["series_id"] for p in out] == ["s2", "s1"]
    assert out[0]["amount"] == 29.0
    assert out[1]["owner"] == "shared"


def test_prefill_flags_positions_already_in_plan() -> None:
    existing = [CostPosition.from_dict({"name": "Gym", "owner": "Anna", "amount": 25})]
    out = prefill.propose_positions([_contract("s2", "Gym", "Anna", 29.0)], existing)
    assert out[0]["already_in_plan"] is True


def test_prefill_acceptance_applies_edits_and_maps_shared() -> None:
    proposals = prefill.propose_positions(
        [_contract("s1", "Streamflix", "shared", 12.99), _contract("s2", "Gym", "Anna", 29.0)], []
    )
    positions = prefill.validate_acceptance(
        {"accept": [{"series_id": "s1"}, {"series_id": "s2", "amount": 25, "owner": "Ben"}]},
        proposals,
        {"Anna", "Ben"},
    )
    assert positions[0].is_shared and positions[0].amount == 12.99
    assert positions[1].owner == "Ben" and positions[1].amount == 25.0
    assert positions[1].amount > 0  # plan sign: expense positive


@pytest.mark.parametrize(
    ("item", "code"),
    [
        ({"series_id": "nope"}, "unknown_series"),
        ({"series_id": "s2", "owner": "Mallory"}, "unknown_owner"),
        ({"series_id": "s2", "amount": -3}, "invalid_amount"),
        ({"series_id": "s2", "amount": "9"}, "invalid_amount"),
    ],
)
def test_prefill_rejects_bad_items(item, code) -> None:
    proposals = prefill.propose_positions([_contract("s2", "Gym", "Anna", 29.0)], [])
    with pytest.raises(prefill.PrefillError) as err:
        prefill.validate_acceptance({"accept": [item]}, proposals, {"Anna"})
    assert err.value.code == code


# --- goals --------------------------------------------------------------------


def test_goal_validation_per_kind() -> None:
    owners = {"Anna"}
    g = goals.validate_goal(
        {"kind": "target_by_date", "name": "Trip", "target_amount": 2000,
         "target_date": "2027-06-01", "owner": "Anna"}, owners)
    assert g["target_date"] == "2027-06-01"
    assert goals.validate_goal(
        {"kind": "savings_rate", "name": "Save", "rate_percent": 10}, owners
    )["owner"] == "shared"
    for bad in (
        {"kind": "nope", "name": "x"},
        {"kind": "savings_rate", "name": "x", "rate_percent": 120},
        {"kind": "category_cap", "name": "x", "category": "Bad Cat", "cap_amount": 5},
        {"kind": "target_by_date", "name": "x", "target_amount": 5, "target_date": "soon"},
        {"kind": "savings_rate", "name": "x", "rate_percent": 5, "owner": "Mallory"},
    ):
        with pytest.raises(goals.GoalError):
            goals.validate_goal(bad, owners)


# --- points -------------------------------------------------------------------


def _hass(entities=()):
    hass = MagicMock()
    hass.states.get.side_effect = lambda e: object() if e in entities else None
    hass.services.async_call = AsyncMock()
    return hass


def test_points_target_validation() -> None:
    hass = _hass({"counter.points", "light.x"})
    assert pts.validate_target(hass, "") == ""
    assert pts.validate_target(hass, "counter.points") == "counter.points"
    for bad in ("light.x", "counter.missing", 5):
        with pytest.raises(pts.PointsTargetError):
            pts.validate_target(hass, bad)


@pytest.mark.asyncio
async def test_award_fires_event_and_increments_helper() -> None:
    hass = _hass({"counter.points"})
    await pts.async_award(hass, target="counter.points", user_id="u1", person="Anna", answered=30)
    hass.bus.async_fire.assert_called_once_with(
        "finance_dashboard_points_awarded",
        {"user_id": "u1", "person": "Anna", "points": 1, "answered_total": 30},
    )
    hass.services.async_call.assert_awaited_once_with(
        "counter", "increment", {"entity_id": "counter.points"}, blocking=False
    )


@pytest.mark.asyncio
async def test_award_without_target_only_fires_event() -> None:
    hass = _hass()
    await pts.async_award(hass, target="", user_id=None, person=None, answered=60)
    hass.bus.async_fire.assert_called_once()
    hass.services.async_call.assert_not_awaited()


def test_person_of_user() -> None:
    persons = [{"name": "Anna", "ha_users": ["u1"]}, {"name": "Ben"}]
    assert pts.person_of_user(persons, "u1") == "Anna"
    assert pts.person_of_user(persons, "zz") is None


# --- AI -----------------------------------------------------------------------


class _Creds:
    def encrypt_json(self, payload):
        return "ENC:" + payload["k"][::-1]

    def decrypt_json(self, token):
        return {"k": token[4:][::-1]}


def test_payload_never_carries_iban_date_or_amount() -> None:
    payload = ai.build_payload(
        "Stadtwerke Musterstadt", "Abschlag 29.10.2026 DE89 3704 0044 0532 0130 00 EUR 54,90"
    )
    text = " ".join(payload.values())
    assert set(payload) == {"merchant", "remittance"}
    for leak in ("DE89", "2026", "54,90", "0130"):
        assert leak not in text
    assert "Abschlag" in text


def test_budget_caps_at_hard_limit_and_resets_monthly() -> None:
    cfg = ai.default_config()
    cfg["budget_cap"] = 2
    assert ai.spend_call(cfg, TODAY) and ai.spend_call(cfg, TODAY)
    assert ai.spend_call(cfg, TODAY) is False
    assert ai.usage_view(cfg, TODAY)["remaining"] == 0
    assert ai.usage_view(cfg, date(2026, 11, 1))["calls"] == 0
    assert ai.spend_call(cfg, date(2026, 11, 1)) is True


def test_update_validation_and_key_is_encrypted_never_public() -> None:
    with pytest.raises(ai.AiError):
        ai.validate_update({"budget_cap": 101})
    with pytest.raises(ai.AiError):
        ai.validate_update({"provider": "skynet"})
    with pytest.raises(ai.AiError):
        ai.validate_update({"api_key": "has space"})
    cfg = ai.apply_update(
        ai.default_config(),
        ai.validate_update({"provider": "xai", "api_key": "xai-secret-123"}),
        _Creds(),
    )
    assert "xai-secret-123" not in repr(cfg)
    assert ai.read_key(cfg, _Creds()) == "xai-secret-123"
    view = ai.public_view(cfg, TODAY, True)
    assert view["has_key"] is True and "xai-secret-123" not in repr(view)
    assert view["effective_model"] == "grok-4-fast"
    cleared = ai.apply_update(cfg, {"api_key": ""}, _Creds())
    assert cleared["key_enc"] == ""


def test_parse_category_matches_whole_slug() -> None:
    cats = ["food", "shopping", "leisure"]
    assert ai.parse_category("Category: Shopping.", cats) == "shopping"
    assert ai.parse_category("unknown", cats) is None


@pytest.mark.asyncio
async def test_categorize_requires_opt_in_caches_and_counts(monkeypatch) -> None:
    saved = {}
    store = MagicMock()
    store.async_load = AsyncMock(side_effect=lambda: saved.get("d"))
    store.async_save = AsyncMock(side_effect=lambda d: saved.__setitem__("d", d))
    hass = MagicMock()
    hass.data = {"finance_dashboard": {"_ai_provider_store": store}}
    calls = []

    async def fake_http(_h, provider, model, key, prompt):
        calls.append((provider, model, key, prompt))
        return "shopping"

    monkeypatch.setattr(ai, "_call_http", fake_http)
    creds = _Creds()
    cfg = ai.apply_update(ai.default_config(), {"provider": "xai", "api_key": "k-1"}, creds)
    saved["d"] = cfg
    kw = dict(credentials=creds, merchant_id="shop a", merchant="Shop A",
              remittance="Order 1", categories=["food", "shopping"], today=TODAY)
    assert await ai.async_categorize(hass, opt_in=False, **kw) is None
    assert calls == []
    assert await ai.async_categorize(hass, opt_in=True, **kw) == "shopping"
    assert await ai.async_categorize(hass, opt_in=True, **kw) == "shopping"  # cache hit
    assert len(calls) == 1
    assert ai.usage_view(saved["d"], TODAY)["calls"] == 1
    assert calls[0][2] == "k-1"


# --- nicknames ----------------------------------------------------------------


def test_nicknames_keep_the_key_and_clear_when_empty() -> None:
    persons = [{"name": "Anna", "ha_users": []}, {"name": "Ben"}]
    nicks = wiz.validate_nicknames(
        [{"person": "Anna", "display_name": " Schatz "}, {"person": "Ben", "display_name": ""}],
        persons,
    )
    out = wiz.apply_nicknames(persons, nicks)
    assert out[0]["name"] == "Anna" and out[0]["display_name"] == "Schatz"
    assert "display_name" not in out[1]
    cleared = wiz.apply_nicknames(out, {"Anna": ""})
    assert "display_name" not in cleared[0]


@pytest.mark.parametrize(
    "raw", ["x", [{"person": "Zed", "display_name": "z"}], [{"person": "Anna", "display_name": "x" * 41}]]
)
def test_nickname_validation(raw) -> None:
    with pytest.raises(wiz.SetupError):
        wiz.validate_nicknames(raw, [{"name": "Anna"}])


def test_points_target_survives_state_merge() -> None:
    state = wiz.apply_update(wiz.default_state(), {})
    state["points_target"] = "counter.points"
    assert wiz._merge_state(state)["points_target"] == "counter.points"
