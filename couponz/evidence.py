"""Deterministic claim checks over producer reviewed evidence; not a truth oracle."""
from datetime import date, datetime

COMMON = ("name", "description", "target", "channel", "start", "end", "minimum_spend",
          "cap", "exclusions", "stacking", "tax_included", "mandatory_fees", "currency")
BASIS = ("kind", "model", "quantity", "components", "eligibility", "currency", "tax_included")


def flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from flatten(child, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix, value


def integer_amount(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def check_fact(job, path, value):
    refs = job.get("provenance", {}).get(path, [])
    refs = [refs] if isinstance(refs, str) else refs
    evidence = {e["id"]: e for e in job.get("evidence", [])}
    matches, problems = [], []
    if value is None:
        return {"path": path, "value": value, "status": "unknown", "refs": refs}
    for ref in refs:
        e = evidence.get(ref)
        if not e:
            problems.append("missing_evidence")
            continue
        assertions = e.get("assertions", {})
        if path not in assertions:
            problems.append("unsupported_field")
        elif assertions[path] != value or type(assertions[path]) is not type(value):
            problems.append("conflicting_value")
        elif e.get("reviewed") is not True or not e.get("locator") or not e.get("checked_at"):
            problems.append("unreviewed_or_unlocated")
        elif e.get("kind") == "synthetic" and not job.get("synthetic"):
            problems.append("synthetic_is_not_official")
        elif e.get("kind") not in {"synthetic", "official", "app_recording", "receipt", "poster"}:
            problems.append("untrusted_source")
        else:
            try:
                checked = datetime.fromisoformat(e["checked_at"].replace("Z", "+00:00"))
                if checked.tzinfo is None:
                    raise ValueError("timezone required")
            except (ValueError, TypeError):
                problems.append("invalid_checked_at")
                continue
            matches.append(ref)
    status = "conflict" if problems else ("supported" if matches else "unsupported")
    return {"path": path, "value": value, "status": status, "refs": matches, "issues": problems}


def compare(offers):
    if len(offers) != 2:
        return {"status": "hold", "reason": "comparison_requires_two_offers"}
    a, b = offers
    unknown = [key for key in BASIS if a.get(key) is None or b.get(key) is None]
    mismatch = [key for key in BASIS if a.get(key) != b.get(key)]
    if unknown or mismatch or not all(integer_amount(o.get("price")) and integer_amount(o.get("mandatory_fees")) for o in offers):
        return {"status": "hold", "reason": "basis_unknown_or_mismatch", "unknown": unknown, "mismatch": mismatch}
    if any(o.get("tax_included") is not True and not integer_amount(o.get("tax_amount")) for o in offers):
        return {"status": "hold", "reason": "additional_tax_unknown"}
    totals = [o["price"] + o["mandatory_fees"] + (o.get("tax_amount", 0) if not o["tax_included"] else 0) for o in offers]
    return {"status": "supported", "baseline": totals[0], "alternative": totals[1],
            "saving": totals[0] - totals[1], "basis": list(BASIS), "price_state": "expected"}


def cart(job):
    lines = job.get("cart", {}).get("lines", [])
    coupon = job.get("cart", {}).get("coupon", {})
    if not lines or not all(integer_amount(x.get("unit_price")) and integer_amount(x.get("quantity")) and x["quantity"] > 0 for x in lines):
        return {"status": "hold", "reason": "invalid_cart_lines"}
    subtotal = sum(x["unit_price"] * x["quantity"] for x in lines)
    discount, minimum = coupon.get("amount"), coupon.get("minimum_spend")
    fees = job.get("cart", {}).get("mandatory_fees")
    if not all(integer_amount(x) for x in (discount, minimum, fees)) or subtotal < minimum or discount > subtotal:
        return {"status": "hold", "reason": "coupon_or_costs_unknown_or_ineligible"}
    tax_amount = 0
    if any(o.get("tax_included") is not True for o in job.get("offers", [])):
        tax_amount = job.get("cart", {}).get("tax_amount")
        if not integer_amount(tax_amount):
            return {"status": "hold", "reason": "additional_tax_unknown"}
    rewards = job.get("cart", {}).get("rewards", [])
    ids = [r.get("id") for r in rewards]
    if len(ids) != len(set(ids)) or None in ids:
        return {"status": "hold", "reason": "duplicate_or_missing_reward_id"}
    if any(not integer_amount(r.get("amount")) or not r.get("kind") or not r.get("condition") for r in rewards):
        return {"status": "hold", "reason": "future_reward_unknown"}
    if job.get("cart", {}).get("declared_payable", subtotal-discount+fees+tax_amount) != subtotal-discount+fees+tax_amount:
        return {"status": "hold", "reason": "declared_payable_conflict"}
    return {"status": "supported", "subtotal": subtotal, "immediate_discount": discount,
            "expected_payable": subtotal - discount + fees + tax_amount, "future_rewards": rewards,
            "price_state": "expected", "future_rewards_deducted": False}


def validate(job):
    issues, claims = [], []
    if job.get("schema_version") != 1:
        issues.append("unsupported_schema")
    offers = job.get("offers", [])
    if not offers:
        issues.append("offers_missing")
    try:
        use_date = date.fromisoformat(job["use_date"])
    except (ValueError, KeyError, TypeError):
        use_date = None
        issues.append("planned_use_date_unknown")
    for index, offer in enumerate(offers):
        for key in COMMON:
            if key not in offer or offer[key] is None:
                issues.append(f"offers.{index}.{key}:unknown")
        try:
            start, end = date.fromisoformat(offer["start"]), date.fromisoformat(offer["end"])
            if start > end or not use_date or not start <= use_date <= end:
                issues.append(f"offers.{index}:expired_or_not_active")
        except (ValueError, KeyError, TypeError):
            issues.append(f"offers.{index}:validity_unknown")
        for key in ("price", "mandatory_fees", "minimum_spend", "cap"):
            if key in offer and offer[key] is not None and not integer_amount(offer[key]):
                issues.append(f"offers.{index}.{key}:amount_must_be_nonnegative_integer")
        if offer.get("currency") != "KRW":
            issues.append(f"offers.{index}:currency_not_implemented")
        if type(offer.get("tax_included")) is not bool:
            issues.append(f"offers.{index}:tax_basis_unknown")
        if offer.get("claimed_price", offer.get("price")) != offer.get("price"):
            issues.append(f"offers.{index}:claimed_price_conflict")
        if offer.get("claimed_state") == "paid":
            refs = job.get("provenance", {}).get(f"offers.{index}.price", [])
            refs = [refs] if isinstance(refs, str) else refs
            if not any(e.get("id") in refs and e.get("scope") == "paid_receipt" and e.get("complete") is True for e in job.get("evidence", [])):
                issues.append(f"offers.{index}:paid_state_not_proven")
        if offer.get("claimed_state") == "issued" and not any(e.get("scope") == "issued" and e.get("complete") is True and f"offers.{index}.claimed_state" in e.get("assertions", {}) for e in job.get("evidence", [])):
            issues.append(f"offers.{index}:issued_state_not_proven")
        if "net_spend" in offer:
            issues.append(f"offers.{index}:net_spend_requires_separate_review")
    for root in ("offers", "cart", "steps"):
        if root not in job:
            continue
        values = job[root]
        if isinstance(values, list):
            pairs = ((p, v) for i, x in enumerate(values) for p, v in flatten(x, f"{root}.{i}"))
        else:
            pairs = flatten(values, root)
        for path, value in pairs:
            c = check_fact(job, path, value)
            claims.append(c)
            if c["status"] != "supported":
                issues.append(f"{path}:{c['status']}")
    if "theme" in job:
        c = check_fact(job, "theme", job["theme"])
        claims.append(c)
        if c["status"] != "supported":
            issues.append(f"theme:{c['status']}")
    if job.get("cta"):
        if job["cta"].get("action") not in {"check_conditions", "save_for_reference"} or set(job["cta"]) != {"action"}:
            issues.append("cta_free_text_or_action_requires_producer_review")
    formats = {"single", "comparison", "procedure", "roundup", "cart"}
    fmt = job.get("format")
    if fmt not in formats:
        issues.append("select_one_of_five_formats")
    calculation = None
    if fmt == "comparison":
        calculation = compare(offers)
    elif fmt == "cart":
        calculation = cart(job)
    elif fmt == "procedure" and not job.get("steps"):
        issues.append("procedure_steps_missing")
    elif fmt == "single" and len(offers) != 1:
        issues.append("single_requires_one_offer")
    elif fmt == "roundup" and len(offers) < 2:
        issues.append("roundup_requires_independent_offers")
    if fmt == "roundup" and job.get("linked_purchase"):
        issues.append("linked_purchase_requires_cart_review")
    if job.get("transactions"):
        issues.append("multiple_transactions_not_implemented")
    if fmt == "comparison" and calculation["status"] == "supported" and job.get("declared_saving", calculation["saving"]) != calculation["saving"]:
        issues.append("declared_saving_conflict")
    if calculation and calculation["status"] == "hold":
        issues.append(calculation["reason"])
    if job.get("performance_claim"):
        issues.append("performance_causal_claim_not_supported")
    return {"status": "hold" if issues else "supported", "issues": sorted(set(issues)),
            "claims": claims, "calculation": calculation,
            "verification_boundary": "Producer-reviewed assertions only; no source authenticity or semantic extraction verification.",
            "script_candidate_allowed": not issues,
            "final_claim_allowed": not issues and not job.get("synthetic", False),
            "approval": "NOT RUN", "synthetic": job.get("synthetic", False)}
