"""Original offline synthetic quote-readiness boundary. Never issues an invoice."""

import argparse
import csv
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def amount(value, label, maximum=Decimal("1000000000")):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid-{label}") from exc
    if not result.is_finite() or not ZERO <= result <= maximum:
        raise ValueError(f"invalid-{label}")
    if result != result.quantize(CENT):
        raise ValueError(f"invalid-{label}")
    return result


def integer(value, label, maximum):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError(f"invalid-{label}")
    result = int(value)
    if not 1 <= result <= maximum:
        raise ValueError(f"invalid-{label}")
    return result


def flag(value, label):
    if value not in ("yes", "no"):
        raise ValueError(f"invalid-{label}")
    return value == "yes"


def cents(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def display(value):
    return f"{value:.2f}"


def evaluate(quote, lines, account, policy):
    labeled = [quote, policy, *lines] + ([account] if account is not None else [])
    if any(row.get("classification") != "SYNTHETIC" for row in labeled):
        raise ValueError("this reference requires explicitly SYNTHETIC quote inputs")
    errors, reviews, calculated = [], [], []
    result = {
        "classification": "SYNTHETIC",
        "quote_id": quote.get("quote-id", "missing-id"),
        "state": "needs-data",
        "data_errors": errors,
        "review_reasons": reviews,
        "totals": None,
        "lines": calculated,
    }
    if account is None:
        errors.append("unknown-account")
        return result
    if not lines:
        errors.append("missing-lines")
    if policy.get("po_required") and not str(quote.get("po-reference", "")).strip():
        errors.append("missing-po")
    try:
        cap = amount(policy["discount_caps_pct"][account["tier"]], "discount-cap", Decimal("100"))
        shipping = amount(quote["shipping-usd"], "shipping")
        taxable_shipping = flag(quote["shipping-taxable"], "shipping-taxable")
        requested_terms = integer(quote["requested-terms-days"], "requested-terms", 120)
        approved_terms = integer(account["approved-terms-days"], "approved-terms", 120)
        active = flag(account["active"], "account-active")
        limit = amount(account["credit-limit-usd"], "credit-limit")
        balance = amount(account["open-balance-usd"], "open-balance")
        shipping_rate = amount(policy["tax_rates_pct"][policy["shipping_tax_code"]], "shipping-tax-rate", Decimal("100"))
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
        errors.sort()
        return result
    if not active:
        reviews.append("inactive-account")
    if requested_terms > approved_terms:
        reviews.append("terms-policy")
    seen_lines = set()
    gross_total, discount_total, net_total, line_tax = ZERO, ZERO, ZERO, ZERO
    for line in lines:
        identity = line.get("line-id", "missing-line-id")
        if identity in seen_lines:
            errors.append(f"{identity}:duplicate-line")
            continue
        seen_lines.add(identity)
        if line.get("quote-id") != quote.get("quote-id"):
            errors.append(f"{identity}:quote-mismatch")
            continue
        try:
            quantity = integer(line["quantity"], "quantity", 10000)
            price = amount(line["unit-price-usd"], "unit-price")
            discount = amount(line["discount-pct"], "discount", Decimal("100"))
            tax_code = line["tax-code"]
            if tax_code not in policy["tax_rates_pct"]:
                raise ValueError("unknown-tax-code")
            rate = amount(policy["tax_rates_pct"][tax_code], "tax-rate", Decimal("100"))
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"{identity}:{exc}")
            continue
        gross = cents(price * quantity)
        net = cents(gross * (1 - discount / 100))
        tax = cents(net * rate / 100)
        if discount > cap:
            reviews.append(f"{identity}:discount-policy")
        gross_total += gross
        discount_total += gross - net
        net_total += net
        line_tax += tax
        calculated.append({"line_id": identity, "gross_usd": display(gross), "net_usd": display(net), "tax_usd": display(tax)})
    if not errors:
        shipping_tax = cents(shipping * shipping_rate / 100) if taxable_shipping else ZERO
        total_tax = line_tax + shipping_tax
        total = net_total + shipping + total_tax
        exposure = balance + total
        if exposure > limit:
            reviews.append("credit-limit")
        result["totals"] = {
            "gross_usd": display(gross_total), "discount_usd": display(discount_total),
            "net_usd": display(net_total), "shipping_usd": display(shipping),
            "shipping_tax_usd": display(shipping_tax), "tax_usd": display(total_tax),
            "total_usd": display(total), "credit_exposure_usd": display(exposure),
        }
        result["state"] = "needs-review" if reviews else "ready-for-human-approval"
    else:
        calculated.clear()
    errors.sort()
    reviews.sort()
    calculated.sort(key=lambda row: row["line_id"])
    return result


def read_csv(path):
    if path.stat().st_size > 1_048_576:
        raise ValueError("reference CSV exceeds 1 MiB")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, strict=True))
    if len(rows) > 5000 or any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("reference CSV has too many or ragged rows")
    return rows


def keyed(rows, key):
    result = {}
    for row in rows:
        value = row[key]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise ValueError(f"invalid {key}")
        if value in result:
            raise ValueError(f"duplicate {key}")
        result[value] = row
    return result


def run_batch(data_dir):
    data_dir = Path(data_dir)
    accounts = keyed(read_csv(data_dir / "accounts.csv"), "account-id")
    quotes = keyed(read_csv(data_dir / "quotes.csv"), "quote-id")
    lines = read_csv(data_dir / "quote-lines.csv")
    keyed(lines, "line-id")
    if any(line["quote-id"] not in quotes for line in lines):
        raise ValueError("orphan quote line")
    policy_path = data_dir / "policy.json"
    if policy_path.stat().st_size > 20000:
        raise ValueError("policy exceeds reference limit")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if any(row.get("classification") != "SYNTHETIC" for row in [*accounts.values(), *quotes.values(), *lines, policy]):
        raise ValueError("this reference requires explicitly SYNTHETIC input files")
    if policy["currency"] != "USD" or policy["rounding"] != "ROUND_HALF_UP-per-line-and-shipping-tax":
        raise ValueError("unsupported reference currency or rounding")
    if type(policy.get("po_required")) is not bool:
        raise ValueError("po_required must be a boolean")
    results = [
        evaluate(quote, [line for line in lines if line["quote-id"] == identity], accounts.get(quote["account-id"]), policy)
        for identity, quote in sorted(quotes.items())
    ]
    return {
        "classification": "SYNTHETIC", "artifact_kind": "offline-reference-not-an-invoice",
        "batch_semantics": "Independent quotes; balances are never reserved or mutated.",
        "counts": {state: sum(row["state"] == state for row in results) for state in ("needs-data", "needs-review", "ready-for-human-approval")},
        "quotes": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    args = parser.parse_args()
    try:
        result = run_batch(args.data_dir)
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
