"""Offline content acceptance for fixed original synthetic prime fixtures only."""
import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = {"baseline": "fixtures/submissions.json", "rework": "fixtures/rework-submissions.json"}
RULES = {"equals", "set-equals", "integer-between", "text-min-length", "nonempty-strings-min", "contains-text"}
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELD = re.compile(r"^[a-z][a-z0-9_]*$")
MISSING = object()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def decode_json(text):
    def refuse_constant(value):
        raise ValueError(f"Non-finite JSON constant {value}")
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=refuse_constant)


def read_json(relative):
    result = decode_json((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(result, dict) or result.get("classification") != "SYNTHETIC":
        raise ValueError("Only SYNTHETIC object inputs are supported")
    return result


def read_csv(relative):
    with (ROOT / relative).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Invalid CSV header")
        rows = list(reader)
    if not rows or any(None in row or any(value is None or "\n" in value or "\r" in value for value in row.values()) or row.get("classification") != "SYNTHETIC" for row in rows):
        raise ValueError("Expected complete one-line SYNTHETIC CSV records")
    return rows


def dependency_order(deliverables, dependencies):
    ids = [row["deliverable_id"] for row in deliverables]
    if len(ids) != len(set(ids)) or any(not SLUG.fullmatch(value) for value in ids):
        raise ValueError("Duplicate or invalid deliverable ID")
    edges, seen = {value: [] for value in ids}, set()
    for row in dependencies:
        pair = (row["deliverable_id"], row["depends_on"])
        if pair in seen or pair[0] not in edges or pair[1] not in edges or pair[0] == pair[1]:
            raise ValueError("Invalid, duplicate, or unknown dependency")
        seen.add(pair)
        edges[pair[0]].append(pair[1])
    ordered, visiting, complete = [], set(), set()
    def visit(value):
        if value in visiting:
            raise ValueError("Deliverable dependencies contain a cycle")
        if value in complete:
            return
        visiting.add(value)
        for prerequisite in sorted(edges[value]):
            visit(prerequisite)
        visiting.remove(value)
        complete.add(value)
        ordered.append(value)
    for value in ids:
        visit(value)
    return ordered, edges


def validate_rule(rule, expected):
    if rule not in RULES:
        raise ValueError("Unknown rule; no dynamic evaluation is supported")
    if rule == "equals":
        valid = type(expected) in (str, bool, int)
    elif rule == "set-equals":
        valid = isinstance(expected, list) and bool(expected) and all(isinstance(item, str) and item for item in expected) and len(set(expected)) == len(expected)
    elif rule == "integer-between":
        valid = isinstance(expected, list) and len(expected) == 2 and all(type(item) is int for item in expected) and expected[0] <= expected[1]
    elif rule in ("text-min-length", "nonempty-strings-min"):
        valid = type(expected) is int and 1 <= expected <= 1000
    else:
        valid = isinstance(expected, str) and bool(expected)
    if not valid:
        raise ValueError("Invalid typed rule operand")


def matches(rule, actual, expected):
    validate_rule(rule, expected)
    if actual is MISSING:
        return False
    if rule == "equals":
        return type(actual) is type(expected) and actual == expected
    if rule == "set-equals":
        return isinstance(actual, list) and all(isinstance(item, str) for item in actual) and len(set(actual)) == len(actual) and set(actual) == set(expected)
    if rule == "integer-between":
        return type(actual) is int and expected[0] <= actual <= expected[1]
    if rule == "text-min-length":
        return isinstance(actual, str) and expected <= len(actual.strip()) <= 4096
    if rule == "nonempty-strings-min":
        return isinstance(actual, list) and expected <= len(actual) <= 1000 and all(isinstance(item, str) and item.strip() and len(item) <= 4096 for item in actual) and len(set(actual)) == len(actual)
    return isinstance(actual, str) and len(actual) <= 4096 and expected in actual


def load_configuration():
    engagement = read_json("case/engagement.json")
    interface = read_json("interfaces/pilot.json")
    boundary = read_json("governance/public-artifact-boundary.json")
    deliverables = read_csv("data/deliverables.csv")
    dependencies = read_csv("data/dependencies.csv")
    raw_matrix = read_csv("data/acceptance-matrix.csv")
    if set(interface["rules"]) != RULES:
        raise ValueError("Interface rule list differs from locally implemented rules")
    if engagement["prime_world"] != boundary["prime_world"] or set(engagement["discovery_only_candidates"]) != set(boundary["candidate_slugs"]):
        raise ValueError("Engagement and boundary disagree")
    if boundary["candidate_relationship"] != "discovery-only" or boundary["approved_external_effects"]:
        raise ValueError("Reference boundary cannot confer exchange authority")
    forbidden = ("foreign_workspace_registration", "membership_operations", "signing_operations", "remote_authority", "federation_activation", "approved_contract")
    if any(boundary[key] is not False for key in forbidden):
        raise ValueError("Reference boundary cannot activate authority")
    order, edges = dependency_order(deliverables, dependencies)
    by_id = {row["deliverable_id"]: row for row in deliverables}
    allowed_candidates = set(boundary["candidate_slugs"])
    for row in deliverables:
        if row["mode"] == "fixture":
            if row["candidate_partner"] not in allowed_candidates:
                raise ValueError("Unknown candidate partner")
        elif row["mode"] != "derived" or row["candidate_partner"] != "federation-prime-contractor":
            raise ValueError("Only the prime may own the derived local report")
        if row["artifact_kind"] not in interface["allowed_artifact_fields"]:
            raise ValueError("Unknown artifact kind")
    matrix, criterion_ids = [], set()
    for number, row in enumerate(raw_matrix, start=2):
        if row["criterion_id"] in criterion_ids or not SLUG.fullmatch(row["criterion_id"]) or row["deliverable_id"] not in by_id:
            raise ValueError("Invalid or duplicate criterion")
        criterion_ids.add(row["criterion_id"])
        if not FIELD.fullmatch(row["field"]):
            raise ValueError("Only explicit top-level business-data fields may be checked")
        kind = by_id[row["deliverable_id"]]["artifact_kind"]
        if row["field"] not in interface["allowed_artifact_fields"][kind]:
            raise ValueError("Criterion references an undeclared artifact field")
        expected = decode_json(row["expected_json"])
        validate_rule(row["rule"], expected)
        matrix.append({**row, "expected": expected, "citation": f"data/acceptance-matrix.csv#row={number}"})
    if {row["deliverable_id"] for row in matrix} != set(by_id):
        raise ValueError("Each deliverable needs an explicit acceptance criterion")
    for candidate in sorted(allowed_candidates):
        brief = read_json(f"briefs/{candidate}.json")
        item = brief["deliverable"]
        if brief["candidate_organization"] != candidate or brief["relationship"] != "discovery-only" or brief["request_state"] != "unsent-and-unapproved":
            raise ValueError("Brief must remain an unapproved discovery-only request")
        if any(value is not False for value in brief["authority"].values()):
            raise ValueError("A reference brief cannot confer authority")
        if item["id"] not in by_id or by_id[item["id"]]["candidate_partner"] != candidate or by_id[item["id"]]["artifact_kind"] != item["artifact_kind"]:
            raise ValueError("Brief and deliverable attribution disagree")
        if set(item["required_fields"]) != set(interface["allowed_artifact_fields"][item["artifact_kind"]]):
            raise ValueError("Brief field contract drift")
        if set(brief["acceptance_ids"]) != {row["criterion_id"] for row in matrix if row["deliverable_id"] == item["id"]} or set(brief["depends_on"]) != set(edges[item["id"]]):
            raise ValueError("Brief acceptance or dependency drift")
    return {"engagement": engagement, "interface": interface, "boundary": boundary, "deliverables": deliverables, "by_id": by_id, "order": order, "edges": edges, "matrix": matrix}


def evaluate(configuration, fixture, source_file):
    expected_root = {"schema", "classification", "scenario", "fixture_only", "submissions"}
    if set(fixture) != expected_root or fixture["schema"] != "synthetic-prime-submissions/1" or fixture["classification"] != "SYNTHETIC" or fixture["fixture_only"] is not True:
        raise ValueError("Only the exact synthetic fixture format is accepted")
    if not isinstance(fixture["submissions"], list) or len(fixture["submissions"]) > 12:
        raise ValueError("Bounded fixture list required")
    by_id, submissions = configuration["by_id"], {}
    envelope_fields = {"deliverable_id", "candidate_partner", "artifact_visibility", "exchange_approval", "artifact"}
    for position, submission in enumerate(fixture["submissions"]):
        if not isinstance(submission, dict) or set(submission) != envelope_fields:
            raise ValueError("Invalid fixture envelope")
        identity = submission["deliverable_id"]
        if identity in submissions or identity not in by_id or by_id[identity]["mode"] != "fixture":
            raise ValueError("Duplicate, undeclared, or derived submission")
        if not isinstance(submission["artifact"], dict):
            raise ValueError("Artifact must be an inert JSON object")
        submissions[identity] = (position, submission)
    results, lookup = [], {}
    for identity in configuration["order"]:
        definition = by_id[identity]
        blocked_by = [item for item in configuration["edges"][identity] if lookup[item]["content_status"] != "content-pass"]
        failures, checks = [], []
        if definition["mode"] == "derived":
            artifact = {"all_upstreams_content_pass": not blocked_by}
            source = "derived-from-local-content-results"
        elif identity not in submissions:
            result = {"deliverable_id": identity, "candidate_partner": definition["candidate_partner"], "content_status": "missing", "blocked_by": blocked_by, "failures": ["Required local fixture is missing"], "checks": []}
            results.append(result); lookup[identity] = result
            continue
        else:
            position, submission = submissions[identity]
            artifact = submission["artifact"]
            source = f"{source_file}#/submissions/{position}/artifact"
            if submission["candidate_partner"] != definition["candidate_partner"]:
                failures.append("Candidate attribution does not match the declared discovery brief")
            if submission["artifact_visibility"] != "public-reference-fixture" or submission["exchange_approval"] != "not-requested":
                failures.append("Only local public-reference fixtures with no exchange approval are accepted")
            allowed = set(configuration["interface"]["allowed_artifact_fields"][definition["artifact_kind"]])
            if set(artifact) != allowed:
                failures.append("Artifact fields differ from the explicit business-data allowlist")
        for criterion in configuration["matrix"]:
            if criterion["deliverable_id"] != identity:
                continue
            actual = artifact.get(criterion["field"], MISSING)
            passed = matches(criterion["rule"], actual, criterion["expected"])
            checks.append({
                "criterion_id": criterion["criterion_id"], "passed": passed,
                "rule": criterion["rule"], "expected": criterion["expected"],
                "actual": None if actual is MISSING else actual, "field_present": actual is not MISSING,
                "matrix_citation": criterion["citation"], "artifact_reference": f"{source}/{criterion['field']}"
            })
            if not passed:
                failures.append(f"{criterion['criterion_id']}: content criterion not satisfied")
        if definition["mode"] == "derived" and blocked_by:
            status = "blocked"
        elif failures:
            status = "rejected"
        elif blocked_by:
            status = "blocked"
        else:
            status = "content-pass"
        result = {"deliverable_id": identity, "candidate_partner": definition["candidate_partner"], "content_status": status, "blocked_by": blocked_by, "failures": failures, "checks": checks}
        results.append(result); lookup[identity] = result
    rework = [{"deliverable_id": row["deliverable_id"], "candidate_partner": row["candidate_partner"], "required_review": row["failures"], "request_sent": False} for row in results if row["content_status"] == "rejected"]
    return {
        "classification": "SYNTHETIC", "scenario": fixture["scenario"], "fixture_only": True,
        "prime_world": configuration["engagement"]["prime_world"],
        "candidate_relationship": "discovery-only",
        "content_pass": all(row["content_status"] == "content-pass" for row in results),
        "criterion_count": len(configuration["matrix"]), "deliverables": results,
        "counts": {status: sum(row["content_status"] == status for row in results) for status in ("content-pass", "rejected", "blocked", "missing")},
        "rework_requests": rework,
        "delivery_authorized": False, "real_partner_submissions": False,
        "owner_exchange_approval": "not-requested",
        "foreign_workspace_registration": False, "federation_activation": False,
        "approved_contract": False, "membership_created": False, "remote_authority": False,
        "external_effects": [],
        "limitation": "Only authored local content is checked. No partner application, real operator, commercial acceptance, or owner-approved exchange is verified."
    }


def run(fixture_name):
    if fixture_name not in FIXTURES:
        raise ValueError("Only explicitly included fixtures may be opened")
    return evaluate(load_configuration(), read_json(FIXTURES[fixture_name]), FIXTURES[fixture_name])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=tuple(FIXTURES), default="baseline")
    args = parser.parse_args()
    try:
        report = run(args.fixture)
    except (ValueError, KeyError, TypeError) as error:
        parser.error(f"Invalid local reference configuration: {error}")
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["content_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
