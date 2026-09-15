# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt
"""Secure, server-side Anthropic (Claude) client for the BS Group app.

Design rules (see bsgroup/ai/README.md):

* The API key lives only in the ``AI Provider Settings`` single doctype as an
  encrypted ``Password`` field. It is read here via ``get_password`` and is
  never returned to a caller, never written to a log, error, comment or the
  browser, and never placed in a URL.
* All calls are made from the server (bench/gunicorn), never the browser.
* This module is Claude-specific by intent. If the configured provider is not
  Anthropic it raises ``AIProviderError`` rather than silently calling a
  different vendor.
* No figures are ever sent to or requested from the model here - that policy
  is enforced by the caller (bsgroup.ai.narrative / quotation_generator).
"""

import json

import frappe
import requests
from frappe import _

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_PROVIDER = "Anthropic (Claude)"
# Default model when AI Provider Settings has none. Kept in step with the model
# the site is actually configured with (claude-sonnet-4-5) and the example shown
# in the Deal Cost Sheet AI dialog. The settings value always takes precedence;
# this is only the fallback so a blank field never sends a retired snapshot id.
DEFAULT_MODEL = "claude-sonnet-4-5"
DEFAULT_MAX_TOKENS = 2000
# Hard ceiling so a mis-configured settings value cannot run away with cost.
MAX_TOKENS_CEILING = 8000
REQUEST_TIMEOUT = 60


class AIProviderError(frappe.ValidationError):
	"""Raised when AI generation cannot proceed (disabled, mis-configured,
	network/API failure). Messages here are always safe to show a user - they
	never contain the API key or raw provider payloads."""


def get_active_config():
	"""Read AI Provider Settings and return a plain config dict.

	Returns a dict with keys: ``enabled``, ``provider``, ``model``,
	``max_tokens``, ``fallback_to_rules``, ``api_key``. The api_key is the
	decrypted secret - keep it local, never log or return it to a client.

	Raises AIProviderError if AI is disabled, the provider is not Anthropic, or
	no API key is configured.
	"""
	settings = frappe.get_cached_doc("AI Provider Settings")

	if not settings.is_enabled:
		raise AIProviderError(_("AI analysis is turned off in AI Provider Settings."))

	provider = (settings.ai_provider or "").strip()
	if provider != ANTHROPIC_PROVIDER:
		raise AIProviderError(
			_("This feature requires the AI provider to be '{0}'. It is currently set to '{1}'.").format(
				ANTHROPIC_PROVIDER, provider or _("(unset)")
			)
		)

	api_key = settings.get_password("api_key", raise_exception=False)
	if not api_key:
		raise AIProviderError(_("No Anthropic API key is configured in AI Provider Settings."))

	try:
		max_tokens = int(settings.max_tokens or DEFAULT_MAX_TOKENS)
	except (TypeError, ValueError):
		max_tokens = DEFAULT_MAX_TOKENS
	max_tokens = max(256, min(max_tokens, MAX_TOKENS_CEILING))

	return {
		"enabled": True,
		"provider": provider,
		"model": (settings.ai_model or "").strip() or DEFAULT_MODEL,
		"max_tokens": max_tokens,
		"fallback_to_rules": bool(settings.fallback_to_rules),
		"api_key": api_key,
	}


def generate(system_prompt, user_message, config=None, timeout=REQUEST_TIMEOUT):
	"""Call Claude with a system prompt and a single user message.

	Returns a dict: ``{"text": str, "model": str, "usage": dict, "stop_reason": str}``.
	Raises AIProviderError on any failure. The API key is never included in any
	raised message or logged payload.
	"""
	config = config or get_active_config()
	api_key = config["api_key"]

	payload = {
		"model": config["model"],
		"max_tokens": config["max_tokens"],
		"system": system_prompt,
		"messages": [{"role": "user", "content": user_message}],
	}
	headers = {
		"x-api-key": api_key,
		"anthropic-version": ANTHROPIC_VERSION,
		"content-type": "application/json",
	}

	try:
		response = requests.post(
			ANTHROPIC_MESSAGES_URL,
			headers=headers,
			data=json.dumps(payload),
			timeout=timeout,
		)
	except requests.exceptions.RequestException as exc:
		# Sanitised logging: only the exception TYPE is recorded. The request
		# payload (the prompt, which carries customer data), the endpoint URL
		# and the api-key header are never logged.
		_update_status(config, ok=False, note="network error")
		frappe.log_error(title="BSG-AI-QUOTATION network error", message=type(exc).__name__)
		raise AIProviderError(_("Could not reach the AI provider (network error). Please try again."))

	if response.status_code != 200:
		# Log only the HTTP status, the configured model, and the provider's
		# error *type* code (e.g. "authentication_error", "not_found_error") -
		# never the response body or the request payload.
		error_type = _provider_error_type(response)
		_update_status(config, ok=False, note=f"HTTP {response.status_code}")
		frappe.log_error(
			title="BSG-AI-QUOTATION provider error",
			message=f"status={response.status_code} model={config.get('model')} type={error_type}",
		)
		if response.status_code == 404 or "not_found" in error_type or "model" in error_type:
			raise AIProviderError(
				_("The AI model configured in AI Provider Settings was not accepted by the provider. Check the Model Name.")
			)
		raise AIProviderError(
			_("The AI provider returned an error (HTTP {0}). Please try again or check AI Provider Settings.").format(
				response.status_code
			)
		)

	try:
		body = response.json()
		text = "".join(
			block.get("text", "")
			for block in body.get("content", [])
			if block.get("type") == "text"
		).strip()
		result = {
			"text": text,
			"model": body.get("model", config["model"]),
			"usage": body.get("usage", {}) or {},
			"stop_reason": body.get("stop_reason", ""),
		}
	except (ValueError, AttributeError, KeyError) as exc:
		# Sanitised: generic to the user, only the exception type server-side.
		_update_status(config, ok=False, note="bad response")
		frappe.log_error(title="BSG-AI-QUOTATION unreadable response", message=type(exc).__name__)
		raise AIProviderError(_("The AI provider returned an unreadable response."))

	if not result["text"]:
		_update_status(config, ok=False, note="empty response")
		raise AIProviderError(_("The AI provider returned an empty response."))

	_update_status(config, ok=True, note="ok")
	return result


def _provider_error_type(response):
	"""Return only the provider's error *type* code (e.g. "authentication_error",
	"not_found_error"), never the free-text message or body - so nothing from the
	request or response payload can reach a log."""
	try:
		err = (response.json() or {}).get("error") or {}
		return str(err.get("type", "") or "")[:60]
	except ValueError:
		return ""


def _update_status(config, ok, note):
	"""Best-effort status write to the AI Provider Settings single. Never
	raises - status telemetry must not break the main flow. Writes no secret."""
	try:
		frappe.db.set_value(
			"AI Provider Settings",
			"AI Provider Settings",
			{
				"gateway_status": ("OK" if ok else f"Error: {note}")[:140],
				"active_provider_display": config.get("provider", ""),
				"last_used": frappe.utils.now(),
			},
			update_modified=False,
		)
	except Exception:
		frappe.clear_last_message()
