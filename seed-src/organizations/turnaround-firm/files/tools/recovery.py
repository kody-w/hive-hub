"""Read-only synthetic cash diagnosis and bounded support-recovery simulation."""
import argparse
import csv
import importlib.util
import json
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEVERITY = {"urgent": 0, "normal": 1, "low": 2}
CATEGORIES = {"subscription-receipts": "in", "payroll": "out", "contractors": "out", "hosting": "out", "refunds": "out"}
SCENARIO_FIELDS = ("subscription_receipts_usd", "payroll_usd", "contractors_usd", "hosting_usd", "refunds_usd")


def amount(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not money")
    number = Decimal(str(value))
    if not number.is_finite() or number < 0 or number != number.quantize(Decimal("0.01")):
        raise ValueError("Finite nonnegative cent amounts required")
    return number


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def integer(value):
    text = str(value)
    if not re.fullmatch(r"0|[1-9]\d*", text):
        raise ValueError("Nonnegative whole count required")
    return int(text)


def calendar(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Exact ISO date required")
    return date.fromisoformat(value)


def read_json(relative):
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if value.get("classification") != "SYNTHETIC":
        raise ValueError("Only SYNTHETIC inputs are supported")
    return value


def read_csv(relative):
    with (ROOT / relative).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Invalid CSV header")
        rows = list(reader)
    if not rows or any(None in row or any(value is None for value in row.values()) or row.get("classification") != "SYNTHETIC" for row in rows):
        raise ValueError("Expected complete SYNTHETIC rows")
    return rows


def reconcile(case, ledger, subscriptions, payables):
    months = case["months"]
    if not months or months != sorted(set(months)) or any(not re.fullmatch(r"\d{4}-\d{2}", month) for month in months):
        raise ValueError("Ordered unique months required")
    first, as_of = calendar(case["opening_date"]), calendar(case["as_of"])
    monthly = {month: {key: Decimal(0) for key in CATEGORIES} for month in months}
    ids = set()
    for row in ledger:
        posted = calendar(row["posted_on"])
        month = row["posted_on"][:7]
        if row["transaction_id"] in ids or month not in monthly or not first <= posted <= as_of:
            raise ValueError("Duplicate or out-of-period ledger entry")
        ids.add(row["transaction_id"])
        if row["category"] not in CATEGORIES or CATEGORIES[row["category"]] != row["direction"]:
            raise ValueError("Cash direction/category mismatch")
        monthly[month][row["category"]] += amount(row["amount_usd"])
    billed = {month: Decimal(0) for month in months}
    accounts = {month: 0 for month in months}
    plan_ids = set()
    for row in subscriptions:
        pair = (row["month"], row["plan"])
        if pair in plan_ids or row["month"] not in monthly:
            raise ValueError("Duplicate or out-of-period subscription cohort")
        plan_ids.add(pair)
        count = integer(row["active_accounts"])
        billed[row["month"]] += count * amount(row["monthly_price_usd"])
        accounts[row["month"]] += count
    opening = amount(case["opening_cash_usd"])
    cash, total_in, total_out, summaries = opening, Decimal(0), Decimal(0), []
    for month in months:
        by_category = monthly[month]
        receipts = by_category["subscription-receipts"]
        if billed[month] != receipts:
            raise ValueError("The authored in-month collection fixture does not reconcile")
        payments = sum((by_category[key] for key, direction in CATEGORIES.items() if direction == "out"), Decimal(0))
        net = receipts - payments
        cash += net
        total_in += receipts
        total_out += payments
        summaries.append({
            "month": month, "receipts_usd": money(receipts), "payments_usd": money(payments),
            "net_cash_usd": money(net), "closing_cash_usd": money(cash),
            "subscription_accounts": accounts[month],
            "categories_usd": {key: money(value) for key, value in by_category.items()}
        })
    reserve, payable_ids = Decimal(0), set()
    for row in payables:
        if row["payable_id"] in payable_ids or row["forecast_treatment"] != "incremental-prior-period-reserve":
            raise ValueError("Duplicate or incorrectly treated payable")
        payable_ids.add(row["payable_id"])
        if calendar(row["due_on"]) <= as_of:
            raise ValueError("This fixture expects unsettled catch-up obligations due after the as-of date")
        reserve += amount(row["amount_usd"])
    return {
        "classification": "SYNTHETIC", "ledger_rows": len(ledger), "opening_cash_usd": money(opening),
        "receipts_usd": money(total_in), "payments_usd": money(total_out), "closing_cash_usd": money(cash),
        "incremental_payables_reserve_usd": money(reserve), "cash_after_reserve_usd": money(cash - reserve),
        "monthly": summaries, "accounting_limit": case["accounting_fixture_assumption"],
        "payables_limit": case["payables_treatment"]
    }


def runway(cash, floor, burn, days_per_month):
    days_per_month = integer(days_per_month)
    if days_per_month <= 0:
        raise ValueError("Positive modeled month length required")
    if cash <= floor:
        return {"days_to_floor": "0.0", "condition": "at-or-below-floor"}
    if burn <= 0:
        return {"days_to_floor": None, "condition": "not-burning-in-this-scenario"}
    days = (cash - floor) / burn * days_per_month
    return {"days_to_floor": format(days.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), ".1f"), "condition": "mechanical-repeat-not-a-forecast"}


def scenario_report(case, cash, rows):
    available = Decimal(cash["cash_after_reserve_usd"])
    floor = amount(case["cash_floor_usd"])
    results, seen = [], set()
    latest = cash["monthly"][-1]["categories_usd"]
    for row in rows:
        if row["scenario_id"] in seen:
            raise ValueError("Duplicate scenario")
        seen.add(row["scenario_id"])
        values = {key: amount(row[key]) for key in SCENARIO_FIELDS}
        if row["scenario_id"] == "repeat-september":
            expected = {"subscription_receipts_usd": latest["subscription-receipts"], **{f"{key}_usd": latest[key] for key in ("payroll", "contractors", "hosting", "refunds")}}
            if values != {key: Decimal(value) for key, value in expected.items()}:
                raise ValueError("Repeated-month scenario differs from the reconciled ledger")
        payments = sum((values[key] for key in SCENARIO_FIELDS[1:]), Decimal(0))
        burn = payments - values["subscription_receipts_usd"]
        results.append({
            "scenario_id": row["scenario_id"], "receipts_usd": money(values["subscription_receipts_usd"]),
            "payments_usd": money(payments), "monthly_burn_usd": money(burn),
            "cash_floor_usd": money(floor),
            "after_reserve_to_zero": runway(available, Decimal(0), burn, case["modeled_days_per_month"]),
            "after_reserve_to_floor": runway(available, floor, burn, case["modeled_days_per_month"]),
            "precondition": row["precondition"], "realized_savings_usd": None, "approved": False
        })
    if "repeat-september" not in seen:
        raise ValueError("Missing reconciled baseline scenario")
    return {"classification": "SYNTHETIC", "scenarios": results, "external_financial_effects": []}


def validate_tickets(rows, as_of):
    cutoff, seen = calendar(as_of), set()
    for row in rows:
        if row["ticket_id"] in seen or not re.fullmatch(r"ticket-\d{3}", row["ticket_id"]):
            raise ValueError("Duplicate or invalid ticket ID")
        seen.add(row["ticket_id"])
        if row["priority"] not in SEVERITY or row["state"] not in ("open", "closed"):
            raise ValueError("Unknown ticket severity or state")
        if calendar(row["opened_on"]) > cutoff:
            raise ValueError("Ticket is in the future")
        if integer(row["estimated_minutes"]) <= 0 or integer(row["affected_accounts"]) <= 0:
            raise ValueError("Positive ticket estimates and affected-account counts required")
        if row["classification"] != "SYNTHETIC":
            raise ValueError("Only synthetic tickets are supported")


def prioritize(rows):
    if any(row["priority"] not in SEVERITY for row in rows):
        raise ValueError("Unknown severity cannot silently become low priority")
    eligible = [row for row in rows if row["state"] == "open" and not row["blocked_by"]]
    return sorted(eligible, key=lambda row: (SEVERITY[row["priority"]], row["opened_on"], row["ticket_id"]))


def select_capacity(rows, minutes):
    if type(minutes) is not int or not 0 <= minutes <= 10000:
        raise ValueError("Capacity must be an integer from 0 to 10000 minutes")
    selected, deferred, used = [], [], 0
    for row in prioritize(rows):
        estimate = integer(row["estimated_minutes"])
        if used + estimate <= minutes:
            selected.append(row)
            used += estimate
        else:
            deferred.append({"ticket_id": row["ticket_id"], "reason": "estimated-work-exceeds-remaining-capacity"})
    return selected, deferred, used


def load_legacy_dispatch():
    spec = importlib.util.spec_from_file_location("authored_defective_dispatch", ROOT / "product/dispatch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def queue_report(case, tickets, capacity):
    validate_tickets(tickets, case["as_of"])
    chosen, deferred, used = select_capacity(tickets, capacity)
    legacy = load_legacy_dispatch().next_batch(tickets, 4)
    candidate_four = prioritize(tickets)[:4]
    blocked = [{"ticket_id": row["ticket_id"], "reason": row["blocked_by"]} for row in tickets if row["state"] == "open" and row["blocked_by"]]
    open_rows = [row for row in tickets if row["state"] == "open"]
    return {
        "classification": "SYNTHETIC", "open_tickets": len(open_rows),
        "total_open_estimated_minutes": sum(integer(row["estimated_minutes"]) for row in open_rows),
        "legacy_first_four": [row["ticket_id"] for row in legacy],
        "candidate_first_four": [row["ticket_id"] for row in candidate_four],
        "capacity_minutes": capacity, "selected_ticket_ids": [row["ticket_id"] for row in chosen],
        "selected_estimated_minutes": used, "selected_urgent_count": sum(row["priority"] == "urgent" for row in chosen),
        "capacity_deferred": deferred, "blocked": blocked,
        "oldest_open_age_days": max(((calendar(case["as_of"]) - calendar(row["opened_on"])).days for row in open_rows), default=None),
        "policy": "Eligible urgent/normal/low; oldest first then ID. Non-preemptive fit can skip a larger ticket; skipped work remains visible.",
        "completed_ticket_ids": [], "deployed": False, "external_effects": []
    }


def build_report(capacity=None):
    case = read_json("case/recovery.json")
    cash = reconcile(case, read_csv("data/cash-ledger.csv"), read_csv("data/subscriptions.csv"), read_csv("data/payables.csv"))
    if capacity is None:
        capacity = case["support_capacity_minutes"]
    queue = queue_report(case, read_csv("data/support-backlog.csv"), capacity)
    scenarios = scenario_report(case, cash, read_csv("data/scenarios.csv"))
    return {"classification": "SYNTHETIC", "as_of": case["as_of"], "cash": cash, "queue": queue, "scenarios": scenarios, "realized_recovery_results": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capacity-minutes", type=int)
    parser.add_argument("--section", choices=("all", "cash", "queue", "scenarios"), default="all")
    args = parser.parse_args()
    report = build_report(args.capacity_minutes)
    print(json.dumps(report if args.section == "all" else report[args.section], indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
