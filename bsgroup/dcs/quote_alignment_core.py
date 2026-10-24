"""Compare a Quotation with its Deal Cost Sheet without touching the database.

Pure functions over plain dicts, so the commercial rules can be exercised
without a Frappe site. ``bsgroup.dcs.quote_alignment`` builds the views from
documents and applies the result to drafts, issue, print and the form banner.

Identity is the DCS child row: each Quotation line names the source rows it
presents in ``sources``. A line may present one row or a bundle of rows; each
quotable row is presented exactly once. Descriptions and order are
presentation and are never compared. Quantities, item codes and money are.
"""
import math

STATE_ORDER = ("matching", "bundled", "repriced", "total_changed", "scope_changed", "stale")
STATE_LABELS = {
	"matching": "Matching", "bundled": "Bundled", "repriced": "Repriced",
	"total_changed": "Total changed", "scope_changed": "Scope changed", "stale": "Stale",
}
QTY_TOLERANCE = 1e-6


def number(value):
	try:
		value = float(value or 0)
	except (TypeError, ValueError, OverflowError):
		return float("nan")
	return value


def finite(value):
	return math.isfinite(number(value))


def precision(currency):
	return 3 if (currency or "").upper() == "OMR" else 2


def money(value, currency):
	return round(number(value), precision(currency))


def tolerance(currency):
	return 0.5 * 10 ** -precision(currency)


def parse_sources(raw):
	"""Return the tokens in order, keeping repeats so duplicates can be reported."""
	if not raw:
		return []
	text = str(raw).replace("\n", ",").replace(";", ",")
	return [token.strip() for token in text.split(",") if token.strip()]


def legacy_signature(sheet, quote):
	"""The pre-mapping rule: the same multiset of (item, qty, selling rate)."""
	currency = sheet.get("currency")
	expected = [(r["item_code"], number(r["qty"]), money(r["selling_rate"], currency))
		for r in sheet["rows"] if r["kind"] == "item"]
	charges = sum(number(r["selling_amount"]) for r in sheet["rows"] if r["kind"] == "charge")
	if charges:
		expected.append((sheet.get("additional_item"), 1.0, money(charges, currency)))
	actual = [(l.get("item_code"), number(l.get("qty")), money(l.get("rate"), currency)) for l in quote["lines"]]
	def key(t):
		return (str(t[0]), t[1], t[2])
	return sorted(expected, key=key) == sorted(actual, key=key)


def analyse(sheet, quote):
	"""Server-derived difference between the quotation and the current DCS position.

	``sheet``: currency, revision_reference, docstatus, superseded, selling_total,
	additional_item, rows [{token, aliases, kind item|charge, item_code, qty,
	selling_rate, selling_amount}], internal_tokens (rows that are never quoted).
	``quote``: currency, revision_reference, net_total, discount_amount,
	additional_discount_percentage, taxes [{charge_type, rate, tax_amount}],
	lines [{idx, item_code, qty, stock_qty, rate, amount, price_list_rate,
	discount_percentage, discount_amount, sources}], legacy_evidence.

	``legacy_evidence`` is server-owned: set only for a quotation that was already
	submitted when row mapping was introduced (``custom_dcs_legacy_basis``). It is
	never inferred from an empty mapping, so removing mappings never relaxes a rule.
	"""
	currency = sheet.get("currency")
	tol = tolerance(currency)
	issues, lines = [], []
	by_token = {}
	for row in sheet["rows"]:
		for token in [row["token"], *list(row.get("aliases") or [])]:
			if token:
				by_token[token] = row
	internal = set(sheet.get("internal_tokens") or [])
	state = set()

	# Stale: the DCS moved on, was replaced, or its living total left its rows.
	if sheet.get("docstatus") != 1:
		state.add("stale")
		issues.append(("dcs_not_submitted", "The Deal Cost Sheet is not submitted."))
	if sheet.get("superseded"):
		state.add("stale")
		issues.append(("dcs_superseded", "The Deal Cost Sheet has been superseded by an amendment."))
	if quote.get("revision_reference") and sheet.get("revision_reference") \
			and quote["revision_reference"] != sheet["revision_reference"]:
		state.add("stale")
		issues.append(("revision_changed", "The DCS revision has changed since this quotation was prepared."))
	rows_selling = sum(number(r["selling_amount"]) for r in sheet["rows"])
	if abs(number(sheet.get("selling_total")) - rows_selling) > tol * max(1, len(sheet["rows"])):
		state.add("stale")
		issues.append(("dcs_rows_out_of_sync", "The living DCS selling total differs from its BOQ rows; "
			"record a BOQ revision before quoting."))

	legacy = bool(quote.get("legacy_evidence"))
	seen = {}
	for line in quote["lines"]:
		for token in parse_sources(line.get("sources")):
			seen[token] = seen.get(token, 0) + 1
	covered = set()
	for line in quote["lines"]:
		tokens = parse_sources(line.get("sources"))
		info = {"idx": line.get("idx"), "sources": tokens, "status": [], "actual_amount": money(line.get("amount"), currency)}
		amount, qty = number(line.get("amount")), number(line.get("stock_qty", line.get("qty")))
		if not all(finite(line.get(f)) for f in ("qty", "rate", "amount", "stock_qty")) or number(line.get("qty")) <= 0 \
				or qty <= 0 or number(line.get("rate")) < 0 or amount < 0:
			info["status"].append("invalid")
			state.add("scope_changed")
		if abs(amount - number(line.get("qty")) * number(line.get("rate"))) > tol * max(1, abs(number(line.get("qty")))):
			info["status"].append("repriced")
			state.add("repriced")
		discount = any(abs(number(line.get(f))) > tol for f in ("discount_percentage", "discount_amount"))
		plr = number(line.get("price_list_rate"))
		if plr and abs(plr - number(line.get("rate"))) > tol:
			discount = True
		if discount:
			info["status"].append("discounted")
			state.add("repriced")
		if legacy:
			lines.append(info)
			continue
		if not tokens:
			info["status"].append("unmapped")
			state.add("scope_changed")
			lines.append(info)
			continue
		sources = []
		for token in tokens:
			row = by_token.get(token)
			if not row:
				info["status"].append("internal_source" if token in internal else "unknown_source")
				state.add("scope_changed")
			elif seen[token] > 1 or row["token"] in covered or row in sources:
				# Presented more than once: every line involved is flagged; the row is not "uncovered".
				info["status"].append("duplicate_source")
				state.add("scope_changed")
				covered.add(row["token"])
			else:
				sources.append(row)
		for row in sources:
			covered.add(row["token"])
		expected = sum(number(r["selling_amount"]) for r in sources)
		info["expected_amount"] = money(expected, currency)
		items = [r for r in sources if r["kind"] == "item"]
		if len(items) > 1 or (items and len(sources) > 1):
			info["status"].append("bundle")
			state.add("bundled")
		if len(sources) == 1 and items:
			row = items[0]
			if line.get("item_code") != row["item_code"]:
				info["status"].append("item_changed")
				state.add("scope_changed")
			if abs(qty - number(row["qty"])) > QTY_TOLERANCE * max(1, abs(number(row["qty"]))):
				info["status"].append("qty_changed")
				state.add("scope_changed")
		elif sources:
			# A bundle, or a lump-sum charge line, is one complete package: quantity 1 in a
			# 1:1 unit. Exact component coverage is by source rows; no multiplier is allowed.
			if abs(number(line.get("qty")) - 1) > QTY_TOLERANCE or abs(qty - 1) > QTY_TOLERANCE:
				info["status"].append("package_qty")
				state.add("scope_changed")
			allowed = {r["item_code"] for r in items}
			if any(r["kind"] == "charge" for r in sources):
				allowed.add(sheet.get("additional_item"))
			if line.get("item_code") not in allowed:
				info["status"].append("item_changed")
				state.add("scope_changed")
		if sources and abs(amount - expected) > tol * max(1, len(sources)):
			info["status"].append("repriced")
			state.add("repriced")
		lines.append(info)

	uncovered = []
	if legacy:
		if not legacy_signature(sheet, quote):
			state.add("scope_changed")
			issues.append(("legacy_differs", "This pre-mapping quotation differs from the DCS BOQ."))
	else:
		uncovered = [r["token"] for r in sheet["rows"] if r["token"] not in covered]
		if uncovered:
			state.add("scope_changed")
			issues.append(("uncovered", f"{len(uncovered)} DCS row(s) are not presented on any quotation line."))
	unknown = sorted({t for l in lines for t in l["sources"] if t not in by_token})
	duplicates = sorted(t for t, n in seen.items() if n > 1)
	if unknown:
		issues.append(("unknown_source", "Some lines name rows that are not quotable rows of this DCS."))
	if duplicates:
		issues.append(("duplicate_source", "Some DCS rows are presented on more than one line."))
	for code, label in (("unmapped", "not mapped to DCS rows"), ("item_changed", "item changed"),
			("qty_changed", "quantity changed"), ("package_qty", "bundle or charge not a single package"),
			("repriced", "repriced"), ("discounted", "discounted"), ("invalid", "invalid figures")):
		count = sum(1 for l in lines if code in l["status"])
		if count:
			issues.append(("line_" + code, f"{count} line(s) {label}."))

	# Total: every discount path lowers the net offer; charges via taxes alter it.
	quote_net = number(quote.get("net_total"))
	dcs_selling = number(sheet.get("selling_total"))
	totals = [quote_net] + ([number(quote["total"])] if quote.get("total") is not None else [])
	if any(abs(t - dcs_selling) > tol * max(1, len(quote["lines"])) for t in totals):
		state.add("total_changed")
		issues.append(("total", "Quotation net selling differs from the DCS selling total."))
	if abs(number(quote.get("discount_amount"))) > tol or abs(number(quote.get("additional_discount_percentage"))) > 0:
		state.add("total_changed")
		issues.append(("document_discount", "A document-level discount is applied."))
	for tax in quote.get("taxes") or []:
		if tax.get("charge_type") == "Actual" or number(tax.get("rate")) < 0 or number(tax.get("tax_amount")) < -tol:
			state.add("total_changed")
			issues.append(("tax_adjustment", "A tax row adds or deducts a fixed or negative amount."))
			break

	commercial = state - {"bundled", "stale"}
	if not commercial:
		state.add("matching")
	ordered = [s for s in STATE_ORDER if s in state]
	return {
		"states": ordered,
		"labels": [STATE_LABELS[s] for s in ordered],
		"matching": "matching" in state,
		"issuable": "matching" in state and "stale" not in state,
		"mapped": not legacy and all(parse_sources(l.get("sources")) for l in quote["lines"]),
		"legacy": legacy,
		"lines": lines,
		"uncovered": uncovered,
		"unknown": unknown,
		"duplicates": duplicates,
		"issues": [{"code": c, "message": m} for c, m in issues],
		"dcs_selling": money(dcs_selling, currency),
		"quote_net": money(quote_net, currency),
		"variance": money(quote_net - dcs_selling, currency),
		"currency": currency,
	}


INITIAL_CLEAR_STATES = ("", "Not Started", "In Negotiation")


def initial_authority(state, required_stored, required_now, selling, approval_matches=False):
	"""Authority for a position with no living revision yet (revision 0), under the existing policy.

	``required_now`` is the existing ``negotiation.requirement`` for the sheet's own
	totals (no concession). Rejection, return and blocking always refuse; a required
	approval must be on record for exactly these totals; an unrecognised state never
	authorises. Returns "" when authorised, else the reason.
	"""
	state = state or ""
	if not finite(selling) or number(selling) <= 0:
		return "The DCS has no positive selling position to issue."
	if state in ("Rejected", "Returned for Rework"):
		return ("The current DCS position was " + state.lower()
			+ ". A new commercial revision and fresh approval are required before issue.")
	if "Blocked" in (required_stored, required_now) or state == "Blocked":
		return "The current DCS position is blocked and cannot be authorised."
	needed = required_now == "Manager" or required_stored not in (None, "", "None")
	if state == "Approved":
		if not needed or approval_matches:
			return ""
		return "The recorded approval does not match the current DCS figures. Fresh approval is required before issue."
	if needed:
		return ("The current DCS position requires recorded commercial approval. Initialise the living position "
			"and obtain approval through the existing route before issue.")
	if state in INITIAL_CLEAR_STATES:
		return ""
	return f"The DCS approval state '{state}' is not a clear state. Review the position before issue."


def row_label(kind, position, text, qty, uom):
	"""Customer-appropriate label for the mapping dialog: row number, description, quantity and unit."""
	text = " ".join(str(text or "").split())
	if len(text) > 120:
		text = text[:117] + "..."
	prefix = ("Row " if kind == "item" else "Charge ") + str(position)
	amount = f"{number(qty):g}" + (f" {uom}" if uom else "")
	return f"{prefix}: {text} - {amount}" if text else f"{prefix} - {amount}"


def payment_terms_wording(rows):
	"""Suggested customer wording from a Payment Terms Template's actual rows, for the user to confirm.

	Never used without confirmation; never a template name. Early-payment discounts are stated.
	"""
	parts = []
	for r in rows or []:
		portion = f"{number(r.get('invoice_portion')):g}%"
		label = " ".join(str(r.get("description") or r.get("payment_term") or "").split())
		basis = r.get("due_date_based_on") or "Day(s) after invoice date"
		days, months = int(number(r.get("credit_days"))), int(number(r.get("credit_months")))
		if basis == "Month(s) after the end of the invoice month":
			due = f"due {months} month(s) after the end of the invoice month"
		elif basis == "Day(s) after the end of the invoice month":
			due = f"due {days} day(s) after the end of the invoice month"
		else:
			due = "due on invoice" if not days else f"due {days} day(s) after invoice date"
		text = f"{portion} {label}, {due}" if label else f"{portion} {due}"
		if number(r.get("discount")) > 0:
			kind = "%" if r.get("discount_type") == "Percentage" else " (amount)"
			text += (f"; {number(r.get('discount')):g}{kind} early-payment discount within "
				f"{int(number(r.get('discount_validity')))} {str(r.get('discount_validity_based_on') or 'day(s)').lower()}")
		parts.append(text)
	return "; ".join(parts) + ("." if parts else "")


def headline(result):
	if result["issuable"]:
		return "Matches the current DCS position."
	parts = ", ".join(result["labels"]) or "Not matching"
	return f"Differs from the current DCS position: {parts}."


def suggest(sheet, quote):
	"""Unambiguous mapping suggestions for unmapped lines; never guesses between candidates.

	A line is suggested only when exactly one unpresented row has the same item,
	quantity and selling amount, and no other unmapped line competes for it.
	"""
	currency = sheet.get("currency")
	tol = tolerance(currency)
	taken = {t for l in quote["lines"] for t in parse_sources(l.get("sources"))}
	free = [r for r in sheet["rows"] if r["token"] not in taken and r["kind"] == "item"]
	candidates = {}
	for line in quote["lines"]:
		if parse_sources(line.get("sources")):
			continue
		qty = number(line.get("stock_qty", line.get("qty")))
		hits = [r for r in free if r["item_code"] == line.get("item_code")
			and abs(qty - number(r["qty"])) <= QTY_TOLERANCE * max(1, abs(number(r["qty"])))
			and abs(number(line.get("amount")) - number(r["selling_amount"])) <= tol]
		candidates[line.get("idx")] = hits
	claims = {}
	for idx, hits in candidates.items():
		for r in hits:
			claims.setdefault(r["token"], []).append(idx)
	out = {}
	for idx, hits in candidates.items():
		if len(hits) == 1 and len(claims[hits[0]["token"]]) == 1:
			out[idx] = hits[0]["token"]
	charges = [r for r in sheet["rows"] if r["kind"] == "charge" and r["token"] not in taken]
	if charges:
		total = sum(number(r["selling_amount"]) for r in charges)
		fits = [l for l in quote["lines"] if not parse_sources(l.get("sources")) and l.get("idx") not in out
			and l.get("item_code") == sheet.get("additional_item") and abs(number(l.get("amount")) - total) <= tol * len(charges)]
		if len(fits) == 1:
			out[fits[0].get("idx")] = ",".join(r["token"] for r in charges)
	return out
