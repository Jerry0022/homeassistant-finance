"""Opt-in AI categorisation: provider settings, monthly call budget, merchant cache.

Rules (CLAUDE.md security rule 6, product-concept § AI categorisation):

* opt-in only (``setup_wizard`` state ``ai_opt_in``); nothing is sent otherwise
* provider: Home Assistant's own AI first (``ha``), or an own API key for xAI
  (Grok), Anthropic (Claude) or OpenAI (ChatGPT)
* payload is ONLY merchant + remittance text - never amount, IBAN or date; the
  remittance is scrubbed of IBAN-, date- and long-number-looking text first
* hard cap of ``HARD_CAP`` calls per calendar month (persisted, resets monthly);
  an attempt counts, a failed call is not retried
* results are cached per merchant permanently
* the API key is Fernet-encrypted (credential manager) in its own Store and is
  never logged or returned by any endpoint
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.ai_provider"
STORAGE_VERSION = 1
HARD_CAP = 100
REQUEST_TIMEOUT = 20
MAX_REMITTANCE = 140
MAX_MERCHANT = 80
MAX_CACHE = 5000

PROVIDER_HA = "ha"
# provider -> (endpoint, default model). The default models are cheap, current
# aliases of each vendor and stay user-configurable.
PROVIDERS: dict[str, tuple[str, str]] = {
    PROVIDER_HA: ("", ""),
    "xai": ("https://api.x.ai/v1/chat/completions", "grok-4-fast"),
    "anthropic": ("https://api.anthropic.com/v1/messages", "claude-haiku-4-5"),
    "openai": ("https://api.openai.com/v1/chat/completions", "gpt-5-mini"),
}
KEYED = ("xai", "anthropic", "openai")

_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{3,4}){3,8}\b", re.I)
_DATE = re.compile(r"\b\d{1,4}[./-]\d{1,2}[./-]\d{1,4}\b")
_LONG_NUM = re.compile(r"\d[\d.,\s]{4,}\d")
_AMOUNT = re.compile(r"[-+]?\d+[.,]\d{2}\s?(?:eur|€)?", re.I)


class AiError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code


def default_config() -> dict[str, Any]:
    return {
        "provider": PROVIDER_HA,
        "model": "",
        "ha_agent": "",
        "budget_cap": HARD_CAP,
        "key_enc": "",
        "usage": {"month": "", "calls": 0},
        "cache": {},
    }


def month_key(today: date) -> str:
    return f"{today.year}-{today.month:02d}"


def sanitize(text: str, limit: int) -> str:
    """Strip IBANs, dates, amounts and long numbers; collapse whitespace; truncate."""
    for pattern in (_IBAN, _DATE, _AMOUNT, _LONG_NUM):
        text = pattern.sub(" ", text)
    return " ".join(text.split())[:limit]


def build_payload(merchant: str, remittance: str) -> dict[str, str]:
    """The ONLY data that ever leaves the system."""
    return {
        "merchant": sanitize(merchant, MAX_MERCHANT),
        "remittance": sanitize(remittance, MAX_REMITTANCE),
    }


def build_prompt(payload: dict[str, str], categories: list[str]) -> str:
    return (
        "Classify a bank-statement merchant into exactly one category. "
        f"Allowed categories: {', '.join(categories)}. "
        "Answer with the category slug only.\n"
        f"Merchant: {payload['merchant']}\nPurpose: {payload['remittance']}"
    )


def parse_category(text: str, categories: list[str]) -> str | None:
    """First allowed category slug found in the model answer."""
    answer = (text or "").strip().lower()
    for cat in categories:
        if re.search(rf"(?<![a-z_]){re.escape(cat)}(?![a-z_])", answer):
            return cat
    return None


# ---------------------------------------------------------------------------
# Config + budget (pure)
# ---------------------------------------------------------------------------


def merge_config(raw: Any) -> dict[str, Any]:
    cfg = default_config()
    if not isinstance(raw, dict):
        return cfg
    if raw.get("provider") in PROVIDERS:
        cfg["provider"] = raw["provider"]
    cfg["model"] = str(raw.get("model") or "")[:80]
    cfg["ha_agent"] = str(raw.get("ha_agent") or "")[:120]
    cap = raw.get("budget_cap")
    if isinstance(cap, int) and not isinstance(cap, bool) and 0 <= cap <= HARD_CAP:
        cfg["budget_cap"] = cap
    cfg["key_enc"] = str(raw.get("key_enc") or "")
    usage = raw.get("usage")
    if isinstance(usage, dict):
        cfg["usage"] = {
            "month": str(usage.get("month") or ""),
            "calls": max(0, int(usage.get("calls") or 0)),
        }
    cache = raw.get("cache")
    cfg["cache"] = (
        {str(k): str(v) for k, v in cache.items()} if isinstance(cache, dict) else {}
    )
    return cfg


def usage_view(cfg: dict[str, Any], today: date) -> dict[str, Any]:
    """Calls this month, the cap and what is left (rolls over on a new month)."""
    month = month_key(today)
    used = cfg["usage"]["calls"] if cfg["usage"]["month"] == month else 0
    cap = min(int(cfg["budget_cap"]), HARD_CAP)
    return {
        "month": month,
        "calls": used,
        "cap": cap,
        "hard_cap": HARD_CAP,
        "remaining": max(0, cap - used),
    }


def spend_call(cfg: dict[str, Any], today: date) -> bool:
    """Reserve one call; False when the monthly cap is reached."""
    view = usage_view(cfg, today)
    if view["remaining"] <= 0:
        return False
    cfg["usage"] = {"month": view["month"], "calls": view["calls"] + 1}
    return True


def validate_update(body: dict[str, Any]) -> dict[str, Any]:
    """Validate the PUT body; returns only the keys to change. Raises :class:`AiError`."""
    out: dict[str, Any] = {}
    if "provider" in body:
        if body["provider"] not in PROVIDERS:
            raise AiError("invalid_provider", "provider must be ha, xai, anthropic or openai")
        out["provider"] = body["provider"]
    for key, limit in (("model", 80), ("ha_agent", 120)):
        if key in body:
            if not isinstance(body[key], str) or len(body[key]) > limit:
                raise AiError(f"invalid_{key}", f"{key} must be a short string")
            out[key] = body[key].strip()
    if "budget_cap" in body:
        cap = body["budget_cap"]
        if isinstance(cap, bool) or not isinstance(cap, int) or not 0 <= cap <= HARD_CAP:
            raise AiError("invalid_budget_cap", f"budget_cap must be an integer 0-{HARD_CAP}")
        out["budget_cap"] = cap
    if "api_key" in body:
        key = body["api_key"]
        if not isinstance(key, str) or len(key) > 400 or any(c.isspace() for c in key.strip()):
            raise AiError("invalid_api_key", "api_key must be a string without whitespace")
        out["api_key"] = key.strip()
    return out


# ---------------------------------------------------------------------------
# Persistence + key
# ---------------------------------------------------------------------------


def _store(hass: HomeAssistant) -> Store:
    data = hass.data.setdefault(DOMAIN, {})
    store = data.get("_ai_provider_store")
    if store is None:
        store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        data["_ai_provider_store"] = store
    return store


async def async_load_config(hass: HomeAssistant) -> dict[str, Any]:
    try:
        raw = await _store(hass).async_load()
    except Exception:  # noqa: BLE001 - a broken file must not block setup
        raw = None
    return merge_config(raw)


async def async_save_config(hass: HomeAssistant, cfg: dict[str, Any]) -> None:
    await _store(hass).async_save(cfg)


def apply_update(cfg: dict[str, Any], changes: dict[str, Any], credentials: Any) -> dict[str, Any]:
    """New config with ``changes`` applied; the key is encrypted, never kept plain."""
    new = merge_config(cfg)
    for key in ("provider", "model", "ha_agent", "budget_cap"):
        if key in changes:
            new[key] = changes[key]
    if "api_key" in changes:
        key = changes["api_key"]
        if key and credentials is None:
            raise AiError("unavailable", "Credential store not ready")
        new["key_enc"] = credentials.encrypt_json({"k": key}) if key else ""
    return new


def read_key(cfg: dict[str, Any], credentials: Any) -> str | None:
    if not cfg["key_enc"] or credentials is None:
        return None
    try:
        return str(credentials.decrypt_json(cfg["key_enc"]).get("k") or "") or None
    except Exception:  # noqa: BLE001 - lost key / damaged token
        _LOGGER.warning("Stored AI key could not be decrypted")
        return None


def public_view(cfg: dict[str, Any], today: date, opt_in: bool) -> dict[str, Any]:
    """What GET returns - the key itself is never part of it."""
    provider = cfg["provider"]
    return {
        "opt_in": opt_in,
        "provider": provider,
        "model": cfg["model"],
        "effective_model": cfg["model"] or PROVIDERS[provider][1],
        "ha_agent": cfg["ha_agent"],
        "has_key": bool(cfg["key_enc"]),
        "budget": usage_view(cfg, today),
        "cached_merchants": len(cfg["cache"]),
        "providers": [
            {
                "id": p,
                "needs_key": p in KEYED,
                "default_model": m,
                "host": endpoint.split("/")[2] if endpoint else "",
            }
            for p, (endpoint, m) in PROVIDERS.items()
        ],
    }


# ---------------------------------------------------------------------------
# Provider calls
# ---------------------------------------------------------------------------


async def _call_http(
    hass: HomeAssistant, provider: str, model: str, key: str, prompt: str
) -> str | None:
    endpoint = PROVIDERS[provider][0]
    session = async_get_clientsession(hass)
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        body = {"model": model, "max_tokens": 20, "messages": [{"role": "user", "content": prompt}]}
    else:  # OpenAI-compatible (xAI, OpenAI)
        headers = {"Authorization": f"Bearer {key}"}
        body = {
            "model": model,
            "max_tokens": 20,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
    async with session.post(endpoint, json=body, headers=headers, timeout=REQUEST_TIMEOUT) as resp:
        if resp.status != 200:  # noqa: PLR2004
            _LOGGER.warning("AI provider %s answered HTTP %s", provider, resp.status)
            return None
        data = await resp.json()
    if provider == "anthropic":
        return "".join(b.get("text", "") for b in data.get("content", []) if isinstance(b, dict))
    return str(data["choices"][0]["message"]["content"])


async def _call_ha(hass: HomeAssistant, agent: str, prompt: str) -> str | None:
    """HA's own AI: AI Task when available, else a conversation agent."""
    if hass.services.has_service("ai_task", "generate_data"):
        data: dict[str, Any] = {"task_name": "finance_categorize", "instructions": prompt}
        if agent:
            data["entity_id"] = agent
        res = await hass.services.async_call(
            "ai_task", "generate_data", data, blocking=True, return_response=True
        )
        return str((res or {}).get("data") or "") or None
    if hass.services.has_service("conversation", "process"):
        data = {"text": prompt}
        if agent:
            data["agent_id"] = agent
        res = await hass.services.async_call(
            "conversation", "process", data, blocking=True, return_response=True
        )
        speech = ((res or {}).get("response") or {}).get("speech") or {}
        return str((speech.get("plain") or {}).get("speech") or "") or None
    return None


async def async_categorize(
    hass: HomeAssistant,
    *,
    credentials: Any,
    opt_in: bool,
    merchant_id: str,
    merchant: str,
    remittance: str,
    categories: list[str],
    today: date,
) -> str | None:
    """Category for a merchant, or None (no opt-in, cap reached, error, no match)."""
    if not opt_in or not categories:
        return None
    cfg = await async_load_config(hass)
    cached = cfg["cache"].get(merchant_id)
    if cached:
        return cached
    provider = cfg["provider"]
    key = None
    if provider in KEYED:
        key = read_key(cfg, credentials)
        if not key:
            return None
    if not spend_call(cfg, today):
        return None
    await async_save_config(hass, cfg)  # persist the spend before the call
    prompt = build_prompt(build_payload(merchant, remittance), categories)
    try:
        if provider == PROVIDER_HA:
            answer = await _call_ha(hass, cfg["ha_agent"], prompt)
        else:
            model = cfg["model"] or PROVIDERS[provider][1]
            answer = await _call_http(hass, provider, model, key or "", prompt)
    except Exception as err:  # noqa: BLE001 - never leak provider text or the key
        _LOGGER.warning("AI categorisation failed (%s)", type(err).__name__)
        return None
    category = parse_category(answer or "", categories)
    if category and len(cfg["cache"]) < MAX_CACHE:
        cfg["cache"][merchant_id] = category
        await async_save_config(hass, cfg)
    return category
