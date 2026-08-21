"""Tests for stable account identity and re-link deduplication.

Enable Banking issues a fresh account uid for every PSU session, so the
uid is NOT an identity — re-linking the same bank produced a second set of
entities for the same real account.  The IBAN is the identity.

These tests pin three properties:
1. The same real account keeps ONE key across re-links.
2. Merging a re-link replaces the old record instead of appending.
3. Accounts of other banks survive the merge untouched.
"""

from __future__ import annotations

import pytest

from custom_components.finance_dashboard.account_identity import (
    account_key,
    dedupe_accounts,
    normalize_iban,
)

# ---------------------------------------------------------------------------
# normalize_iban
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DE02120300000000202051", "DE02120300000000202051"),
        ("de02 1203 0000 0000 2020 51", "DE02120300000000202051"),
        ("  DE02-1203-0000-0000-2020-51  ", "DE02120300000000202051"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_iban(raw, expected):
    """Formatting differences must not create a second identity."""
    assert normalize_iban(raw) == expected


# ---------------------------------------------------------------------------
# account_key
# ---------------------------------------------------------------------------


def test_key_is_stable_across_new_session_uid():
    """A new Enable Banking uid for the same IBAN must yield the same key."""
    first = {"id": "uid-session-1", "iban": "DE02120300000000202051", "institution_id": "DKB"}
    second = {"id": "uid-session-2", "iban": "DE02 1203 0000 0000 2020 51", "institution_id": "DKB"}
    assert account_key(first) == account_key(second)


def test_key_differs_per_account():
    """Two different IBANs at the same bank must not collide."""
    a = {"id": "x", "iban": "DE02120300000000202051", "institution_id": "DKB"}
    b = {"id": "y", "iban": "DE02120300000000202052", "institution_id": "DKB"}
    assert account_key(a) != account_key(b)


def test_key_leaks_no_iban():
    """The key ends up in the entity registry — it must not carry the IBAN."""
    iban = "DE02120300000000202051"
    key = account_key({"id": "x", "iban": iban, "institution_id": "DKB"})
    assert iban not in key
    assert iban[-4:] not in key


def test_key_falls_back_to_uid_without_iban():
    """Accounts without an IBAN (some card products) still need a key."""
    acc = {"id": "card-uid-1", "iban": "", "institution_id": "DKB"}
    assert account_key(acc)
    assert account_key(acc) == account_key(dict(acc))


def test_key_without_iban_is_not_shared_between_accounts():
    """Two IBAN-less accounts must not collapse into one entity."""
    a = {"id": "card-uid-1", "iban": "", "institution_id": "DKB"}
    b = {"id": "card-uid-2", "iban": "", "institution_id": "DKB"}
    assert account_key(a) != account_key(b)


# ---------------------------------------------------------------------------
# dedupe_accounts
# ---------------------------------------------------------------------------


def _acc(uid, iban, inst="DKB", **extra):
    return {"id": uid, "iban": iban, "institution_id": inst, "institution": inst, **extra}


def test_relink_same_bank_does_not_duplicate():
    """Re-linking the same account must replace, not append."""
    existing = [_acc("uid-1", "DE02120300000000202051", custom_name="Girokonto")]
    incoming = [_acc("uid-2", "DE02120300000000202051")]

    merged = dedupe_accounts(existing, incoming)

    assert len(merged) == 1
    assert merged[0]["id"] == "uid-2"  # fresh session uid wins


def test_relink_preserves_user_settings():
    """User-owned fields must survive a re-link — they are not bank data."""
    existing = [
        _acc(
            "uid-1",
            "DE02120300000000202051",
            custom_name="Haushaltskonto",
            type="shared",
            person="Jeremy",
            ha_users=[{"id": "u1", "name": "Jeremy"}],
        )
    ]
    incoming = [_acc("uid-2", "DE02120300000000202051")]

    merged = dedupe_accounts(existing, incoming)

    assert merged[0]["custom_name"] == "Haushaltskonto"
    assert merged[0]["type"] == "shared"
    assert merged[0]["person"] == "Jeremy"
    assert merged[0]["ha_users"] == [{"id": "u1", "name": "Jeremy"}]


def test_incoming_settings_win_when_explicitly_set():
    """An assignment made in the wizard must override the stored one."""
    existing = [_acc("uid-1", "DE02120300000000202051", custom_name="Alt", type="personal")]
    incoming = [_acc("uid-2", "DE02120300000000202051", custom_name="Neu", type="shared")]

    merged = dedupe_accounts(existing, incoming)

    assert merged[0]["custom_name"] == "Neu"
    assert merged[0]["type"] == "shared"


def test_other_banks_survive():
    """Accounts of an unrelated bank must not be touched."""
    existing = [
        _acc("ing-1", "DE89370400440532013000", inst="ING"),
        _acc("dkb-1", "DE02120300000000202051", inst="DKB"),
    ]
    incoming = [_acc("dkb-2", "DE02120300000000202051", inst="DKB")]

    merged = dedupe_accounts(existing, incoming)

    assert len(merged) == 2
    assert {a["institution_id"] for a in merged} == {"ING", "DKB"}


def test_stale_accounts_of_same_bank_are_dropped():
    """A closed account must disappear on re-link of that bank."""
    existing = [
        _acc("dkb-1", "DE02120300000000202051"),
        _acc("dkb-old", "DE02120300000000209999"),
    ]
    incoming = [_acc("dkb-2", "DE02120300000000202051")]

    merged = dedupe_accounts(existing, incoming)

    assert len(merged) == 1
    assert merged[0]["id"] == "dkb-2"


def test_duplicates_inside_one_payload_are_collapsed():
    """The API itself can list the same IBAN twice (DKB card duplicates)."""
    incoming = [
        _acc("dkb-1", "DE02120300000000202051"),
        _acc("dkb-1-dup", "DE02 1203 0000 0000 2020 51"),
    ]

    merged = dedupe_accounts([], incoming)

    assert len(merged) == 1


def test_every_merged_account_carries_its_key():
    """The key is persisted so entity identity survives a restart."""
    merged = dedupe_accounts([], [_acc("dkb-1", "DE02120300000000202051")])
    assert merged[0]["key"] == account_key(merged[0])


def test_existing_key_is_not_rewritten():
    """A stored key stays authoritative even if the IBAN changes format."""
    existing = [_acc("dkb-1", "DE02120300000000202051", key="legacy-key-value")]
    incoming = [_acc("dkb-2", "DE02 1203 0000 0000 2020 51")]

    merged = dedupe_accounts(existing, incoming)

    assert len(merged) == 1
    assert merged[0]["key"] == "legacy-key-value"


# ---------------------------------------------------------------------------
# Entity registry reconciliation
# ---------------------------------------------------------------------------


class _RegEntry:
    def __init__(self, entity_id, unique_id):
        self.entity_id = entity_id
        self.unique_id = unique_id


class _FakeRegistry:
    def __init__(self, entries):
        self.entries = list(entries)
        self.removed = []

    def async_update_entity(self, entity_id, new_unique_id=None):
        for e in self.entries:
            if e.entity_id == entity_id:
                e.unique_id = new_unique_id
                return e
        raise AssertionError(f"unknown entity {entity_id}")

    def async_remove(self, entity_id):
        self.removed.append(entity_id)
        self.entries = [e for e in self.entries if e.entity_id != entity_id]


class _FakeEntry:
    entry_id = "entry-1"

    def __init__(self, accounts):
        self.data = {"accounts": accounts}


@pytest.fixture
def registry_patch(monkeypatch):
    """Patch the entity_registry module the reconciler imports."""
    import sys
    import types

    holder = {}

    def _install(entries):
        registry = _FakeRegistry(entries)
        holder["registry"] = registry
        fake_er = types.ModuleType("homeassistant.helpers.entity_registry")
        fake_er.async_get = lambda hass: registry
        fake_er.async_entries_for_config_entry = lambda reg, entry_id: list(reg.entries)
        monkeypatch.setitem(
            sys.modules, "homeassistant.helpers.entity_registry", fake_er
        )
        helpers = sys.modules["homeassistant.helpers"]
        monkeypatch.setattr(helpers, "entity_registry", fake_er, raising=False)
        return registry

    holder["install"] = _install
    return holder


@pytest.mark.asyncio
async def test_legacy_entity_is_migrated_not_duplicated(registry_patch):
    """An entity on the old uid-based id must be rewritten, keeping history."""
    from custom_components.finance_dashboard.account_identity import (
        async_reconcile_account_entities,
        balance_unique_id,
    )

    account = _acc("uid-session-2", "DE02120300000000202051")
    # Registry still holds the entity created under the FIRST session's uid
    legacy = _RegEntry("sensor.fd_dkb_giro", "finance_dashboard_uid-session-2_balance")
    registry = registry_patch["install"]([legacy])

    stats = await async_reconcile_account_entities(
        None, _FakeEntry([account]), "finance_dashboard"
    )

    assert stats == {"migrated": 1, "removed": 0}
    assert legacy.unique_id == balance_unique_id("finance_dashboard", account)
    assert legacy.entity_id == "sensor.fd_dkb_giro"  # entity_id untouched
    assert registry.removed == []


@pytest.mark.asyncio
async def test_orphaned_duplicate_is_removed(registry_patch):
    """A balance entity owned by no linked account must be cleaned up."""
    from custom_components.finance_dashboard.account_identity import (
        async_reconcile_account_entities,
        balance_unique_id,
    )

    account = _acc("uid-2", "DE02120300000000202051")
    current = _RegEntry("sensor.fd_dkb_giro", balance_unique_id("finance_dashboard", account))
    orphan = _RegEntry("sensor.fd_dkb_giro_2", "finance_dashboard_uid-ancient_balance")
    registry = registry_patch["install"]([current, orphan])

    stats = await async_reconcile_account_entities(
        None, _FakeEntry([account]), "finance_dashboard"
    )

    assert stats == {"migrated": 0, "removed": 1}
    assert registry.removed == ["sensor.fd_dkb_giro_2"]


@pytest.mark.asyncio
async def test_non_balance_entities_are_left_alone(registry_patch):
    """Budget numbers and the split select must never be touched."""
    from custom_components.finance_dashboard.account_identity import (
        async_reconcile_account_entities,
    )

    others = [
        _RegEntry("number.fd_budget_wohnen", "finance_dashboard_budget_wohnen"),
        _RegEntry("select.fd_split_model", "finance_dashboard_split_model"),
        _RegEntry("sensor.fd_monthly_summary", "finance_dashboard_monthly_summary"),
    ]
    registry = registry_patch["install"](others)

    stats = await async_reconcile_account_entities(None, _FakeEntry([]), "finance_dashboard")

    assert stats == {"migrated": 0, "removed": 0}
    assert registry.removed == []


@pytest.mark.asyncio
async def test_already_migrated_entity_is_a_noop(registry_patch):
    """Re-running reconciliation must not churn the registry."""
    from custom_components.finance_dashboard.account_identity import (
        async_reconcile_account_entities,
        balance_unique_id,
    )

    account = _acc("uid-2", "DE02120300000000202051")
    entry = _RegEntry("sensor.fd_dkb_giro", balance_unique_id("finance_dashboard", account))
    registry = registry_patch["install"]([entry])

    stats = await async_reconcile_account_entities(
        None, _FakeEntry([account]), "finance_dashboard"
    )

    assert stats == {"migrated": 0, "removed": 0}
    assert registry.removed == []


@pytest.mark.asyncio
async def test_empty_account_list_removes_nothing(registry_patch):
    """No accounts loaded means "unknown", not "all orphaned".

    A config entry can legitimately hold zero accounts while balance
    entities exist: a half-configured setup, a storage-recovery round, or a
    re-auth that failed after the account list was cleared.  Treating that
    as "every entity is an orphan" wipes the user's history irrecoverably.
    """
    from custom_components.finance_dashboard.account_identity import (
        async_reconcile_account_entities,
        balance_unique_id,
    )

    account = _acc("uid-1", "DE02120300000000202051")
    live = _RegEntry("sensor.fd_dkb_giro", balance_unique_id("finance_dashboard", account))
    legacy = _RegEntry("sensor.fd_ing_giro", "finance_dashboard_uid-2_balance")
    registry = registry_patch["install"]([live, legacy])

    stats = await async_reconcile_account_entities(
        None, _FakeEntry([]), "finance_dashboard"
    )

    assert stats == {"migrated": 0, "removed": 0}
    assert registry.removed == []
