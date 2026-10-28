"""Setup-wizard endpoints (admin only, cache/config only - never a bank call).

* ``GET/PUT /api/finance_dashboard/setup``                     wizard state
* ``GET /api/finance_dashboard/setup/payday_suggestions``      per-person payday hints
* ``GET/POST /api/finance_dashboard/setup/pot_suggestions``    pots from history
"""

from __future__ import annotations

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.util import dt as dt_util

from .. import setup_wizard as wiz
from ..const import DOMAIN, OPT_BENCHMARK_POSTCODE, OPT_BENCHMARK_STATE
from ..pots import Pot
from ..transfer_detector import get_effective_transactions
from ._helpers import _get_manager, admin_denied


async def _body(request: web.Request) -> dict | None:
    try:
        data = await request.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _bad(view, err: wiz.SetupError) -> web.Response:
    return view.json({"error": err.code, "detail": err.detail}, status_code=400)


def _options(manager) -> dict:
    entry = getattr(manager, "_entry", None)
    return dict(getattr(entry, "options", None) or {})


def _region(raw) -> dict | None:
    """Benchmark region from the wizard: federal state code + optional postcode."""
    if not isinstance(raw, dict):
        return None
    state = str(raw.get("state") or "").strip().upper()
    postcode = str(raw.get("postcode") or "").strip()
    code = state.removeprefix("DE-")
    if state and not (code.isalpha() and len(code) == 2):
        return None
    if postcode and not (postcode.isdigit() and len(postcode) == 5):
        return None
    return {OPT_BENCHMARK_STATE: state, OPT_BENCHMARK_POSTCODE: postcode}


async def _payload(hass, manager) -> dict:
    state = await wiz.async_load_state(hass)
    accounts = getattr(manager, "_accounts", []) or []
    hints = wiz.data_hints(manager.persons, accounts, len(manager.pots))
    return {
        "current_step": wiz.current_step(state, hints),
        "steps": wiz.effective_steps(state, hints),
        "completed": bool(state["completed"]),
        "ai_opt_in": state["ai_opt_in"],
        "notifications": state["notifications"],
        "persons": [
            {"name": str(p.get("name") or ""), "payday": wiz.person_payday(p)}
            for p in manager.persons
        ],
        "region": {
            "state": _options(manager).get(OPT_BENCHMARK_STATE) or "",
            "postcode": _options(manager).get(OPT_BENCHMARK_POSTCODE) or "",
        },
    }


class FinanceDashboardSetupView(HomeAssistantView):
    """Wizard state: resumes until completed once."""

    url = f"/api/{DOMAIN}/setup"
    name = f"api:{DOMAIN}:setup"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        if (denied := admin_denied(self, request)) is not None:
            return denied
        hass = request.app["hass"]
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)
        return self.json(await _payload(hass, manager))

    async def put(self, request: web.Request) -> web.Response:
        """Body (all optional): step+status, complete, ai_opt_in, notifications, paydays."""
        if (denied := admin_denied(self, request)) is not None:
            return denied
        hass = request.app["hass"]
        manager = _get_manager(hass)
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)
        body = await _body(request)
        if body is None:
            return self.json({"error": "invalid_body", "detail": "Body must be a JSON object"},
                             status_code=400)
        try:
            state = wiz.apply_update(await wiz.async_load_state(hass), body)
            paydays = (
                wiz.validate_paydays(body["paydays"], manager.persons) if "paydays" in body else {}
            )
        except wiz.SetupError as err:
            return _bad(self, err)
        if paydays:
            if getattr(manager, "demo_mode", False):
                return self.json({"error": "demo_mode"}, status_code=400)
            hass.config_entries.async_update_entry(
                manager._entry,  # noqa: SLF001
                data={
                    **manager._entry.data,  # noqa: SLF001
                    "persons": wiz.apply_paydays(manager.persons, paydays),
                },
            )
        if "region" in body:
            region = _region(body["region"])
            if region is None:
                return self.json({"error": "invalid_region"}, status_code=400)
            hass.config_entries.async_update_entry(
                manager._entry,  # noqa: SLF001
                options={**manager._entry.options, **region},  # noqa: SLF001
            )
        await wiz.async_save_state(hass, state)
        return self.json(await _payload(hass, manager))


class FinanceDashboardPaydaySuggestionsView(HomeAssistantView):
    url = f"/api/{DOMAIN}/setup/payday_suggestions"
    name = f"api:{DOMAIN}:setup_payday_suggestions"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        if (denied := admin_denied(self, request)) is not None:
            return denied
        manager = _get_manager(request.app["hass"])
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)
        txs = get_effective_transactions(manager._transactions)  # noqa: SLF001
        return self.json({"suggestions": wiz.suggest_paydays(txs, manager.persons)})


class FinanceDashboardPotSuggestionsView(HomeAssistantView):
    url = f"/api/{DOMAIN}/setup/pot_suggestions"
    name = f"api:{DOMAIN}:setup_pot_suggestions"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        if (denied := admin_denied(self, request)) is not None:
            return denied
        manager = _get_manager(request.app["hass"])
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)
        txs = get_effective_transactions(manager._transactions)  # noqa: SLF001
        today = dt_util.now().date()
        return self.json({"suggestions": wiz.suggest_pots(txs, manager.pots, today)})

    async def post(self, request: web.Request) -> web.Response:
        """Accept suggestions: ``{"accept": [{category, owner, cycle_budget, name?}]}``."""
        if (denied := admin_denied(self, request)) is not None:
            return denied
        manager = _get_manager(request.app["hass"])
        if not manager:
            return self.json({"error": "Not configured"}, status_code=404)
        body = await _body(request)
        try:
            payloads = wiz.validate_pot_acceptance(body)
            for payload in payloads:  # validate everything before saving anything
                Pot.from_dict(payload)
            created = []
            for payload in payloads:
                created.append(await manager.async_save_pot(payload, replace=False))
        except wiz.SetupError as err:
            return _bad(self, err)
        except ValueError as err:
            return self.json({"error": "invalid_pot", "detail": str(err)}, status_code=400)
        return self.json({"ok": True, "pots": created}, status_code=201)
