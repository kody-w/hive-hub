"""Validate synthetic financial consistency and the baseline/candidate contrast."""
import copy
import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("turnaround_recovery", ROOT / "tools/recovery.py")
RECOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVERY)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.case = RECOVERY.read_json("case/recovery.json")
        self.ledger = RECOVERY.read_csv("data/cash-ledger.csv")
        self.subscriptions = RECOVERY.read_csv("data/subscriptions.csv")
        self.payables = RECOVERY.read_csv("data/payables.csv")
        self.tickets = RECOVERY.read_csv("data/support-backlog.csv")

    def test_cash_equation_and_monthly_reconciliation(self):
        cash = RECOVERY.reconcile(self.case, self.ledger, self.subscriptions, self.payables)
        self.assertEqual(cash["ledger_rows"], 15)
        self.assertEqual((cash["opening_cash_usd"], cash["receipts_usd"], cash["payments_usd"], cash["closing_cash_usd"]), ("52000.00", "48500.00", "68100.00", "32400.00"))
        self.assertEqual([row["net_cash_usd"] for row in cash["monthly"]], ["-4000.00", "-6600.00", "-9000.00"])
        self.assertEqual([row["subscription_accounts"] for row in cash["monthly"]], [116, 104, 93])
        self.assertEqual(cash["incremental_payables_reserve_usd"], "5500.00")
        self.assertEqual(cash["cash_after_reserve_usd"], "26900.00")

    def test_runway_and_containment_are_scenarios_not_results(self):
        report = RECOVERY.build_report()
        rows = report["scenarios"]["scenarios"]
        self.assertEqual([row["monthly_burn_usd"] for row in rows], ["9000.00", "7300.00"])
        self.assertEqual(rows[0]["after_reserve_to_zero"]["days_to_floor"], "89.7")
        self.assertEqual(rows[0]["after_reserve_to_floor"]["days_to_floor"], "49.7")
        self.assertEqual(rows[1]["after_reserve_to_floor"]["days_to_floor"], "61.2")
        self.assertEqual(Decimal(rows[0]["monthly_burn_usd"]) - Decimal(rows[1]["monthly_burn_usd"]), Decimal(1700))
        self.assertTrue(all(row["realized_savings_usd"] is None and not row["approved"] for row in rows))

    def test_known_baseline_bug_and_candidate_order(self):
        report = RECOVERY.queue_report(self.case, self.tickets, 420)
        self.assertEqual(report["legacy_first_four"], ["ticket-009", "ticket-002", "ticket-006", "ticket-012"])
        self.assertEqual(report["candidate_first_four"], ["ticket-001", "ticket-010", "ticket-007", "ticket-011"])
        self.assertNotEqual(report["legacy_first_four"], report["candidate_first_four"])

    def test_capacity_slice_preserves_blocked_and_deferred_work(self):
        report = RECOVERY.queue_report(self.case, self.tickets, 420)
        self.assertEqual(report["selected_ticket_ids"], ["ticket-001", "ticket-010", "ticket-007", "ticket-011", "ticket-005", "ticket-008"])
        self.assertEqual((report["selected_estimated_minutes"], report["selected_urgent_count"]), (420, 3))
        self.assertEqual(report["total_open_estimated_minutes"], 690)
        self.assertEqual(report["oldest_open_age_days"], 29)
        self.assertEqual([row["ticket_id"] for row in report["blocked"]], ["ticket-004"])
        self.assertEqual(len(report["capacity_deferred"]), 5)
        accounted = set(report["selected_ticket_ids"]) | {row["ticket_id"] for row in report["blocked"] + report["capacity_deferred"]}
        self.assertEqual(accounted, {row["ticket_id"] for row in self.tickets})
        self.assertEqual(report["completed_ticket_ids"], [])
        self.assertFalse(report["deployed"])

    def test_zero_capacity_and_invalid_capacity(self):
        selected, deferred, used = RECOVERY.select_capacity(self.tickets, 0)
        self.assertEqual((selected, used, len(deferred)), ([], 0, 11))
        for value in (-1, 10001, True, 4.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RECOVERY.select_capacity(self.tickets, value)

    def test_invalid_ticket_inputs_are_rejected(self):
        for changes in ({"priority": "critical-ish"}, {"opened_on": "2026-10-01"}, {"estimated_minutes": "0"}, {"affected_accounts": "-1"}, {"classification": "REAL"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                RECOVERY.validate_tickets([{**self.tickets[0], **changes}], self.case["as_of"])
        with self.assertRaises(ValueError):
            RECOVERY.validate_tickets([self.tickets[0], self.tickets[0]], self.case["as_of"])

    def test_ties_are_deterministic_and_closed_work_is_excluded(self):
        a = {**self.tickets[0], "ticket_id": "ticket-101", "opened_on": "2026-09-01"}
        b = {**a, "ticket_id": "ticket-102"}
        closed = {**a, "ticket_id": "ticket-100", "state": "closed"}
        self.assertEqual([row["ticket_id"] for row in RECOVERY.prioritize([b, closed, a])], ["ticket-101", "ticket-102"])

    def test_duplicate_ledger_and_cohort_drift_are_rejected(self):
        with self.assertRaises(ValueError):
            RECOVERY.reconcile(self.case, self.ledger + [self.ledger[0]], self.subscriptions, self.payables)
        changed = [{**self.subscriptions[0], "active_accounts": "99"}] + self.subscriptions[1:]
        with self.assertRaises(ValueError):
            RECOVERY.reconcile(self.case, self.ledger, changed, self.payables)
        with self.assertRaises(ValueError):
            RECOVERY.reconcile(self.case, self.ledger, self.subscriptions, self.payables + [self.payables[0]])

    def test_invalid_money_and_zero_burn_semantics(self):
        for value in ("NaN", "Infinity", "-1", "0.001", True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RECOVERY.amount(value)
        self.assertIsNone(RECOVERY.runway(Decimal(100), Decimal(10), Decimal(0), 30)["days_to_floor"])
        self.assertEqual(RECOVERY.runway(Decimal(5), Decimal(10), Decimal(100), 30)["days_to_floor"], "0.0")

    def test_repeated_month_scenario_cannot_drift(self):
        cash = RECOVERY.reconcile(self.case, self.ledger, self.subscriptions, self.payables)
        rows = RECOVERY.read_csv("data/scenarios.csv")
        rows[0]["hosting_usd"] = "1801.00"
        with self.assertRaises(ValueError):
            RECOVERY.scenario_report(self.case, cash, rows)

    def test_sprint_budgets_and_dependencies(self):
        rows = RECOVERY.read_csv("ops/recovery-sprint.csv")
        budgets = {bucket: sum(int(row["estimate_minutes"]) for row in rows if row["budget_bucket"] == bucket) for bucket in ("engineering", "support")}
        self.assertEqual(budgets, {"engineering": 360, "support": 420})
        ids = {row["work_id"] for row in rows}
        self.assertTrue(all(not row["depends_on"] or row["depends_on"] in ids for row in rows))

    def test_simulation_leaves_inputs_unchanged(self):
        before = copy.deepcopy(self.tickets)
        RECOVERY.queue_report(self.case, self.tickets, 420)
        self.assertEqual(before, self.tickets)


if __name__ == "__main__":
    unittest.main(verbosity=2)
