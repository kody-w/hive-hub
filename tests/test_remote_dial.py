from __future__ import annotations

import copy
import hashlib
import io
import json
import multiprocessing
import socket
import threading
import time
from contextlib import redirect_stderr, redirect_stdout, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from hive_hub import (
    DialRecord,
    HiveHub,
    LearningArtifact,
    LearningBundle,
    canonical_bytes,
    content_address,
    derive_chant,
)
from hive_hub.cli import main
from hive_hub.filesystem import SafeFilesystem, WritePlan
from hive_hub.limits import MAX_JSON_BYTES, MAX_RECORD_BYTES
from hive_hub.published import PublishedRecord, project_published_record

from .helpers import PROJECT_ROOT, WorkspaceTestCase, files_under


def _slow_dns_worker(connection, url, timeout) -> None:
    from hive_hub._http_fetch import _snapshot_worker

    resolve = socket.getaddrinfo

    def delayed_resolve(*args, **kwargs):
        time.sleep(3)
        return resolve(*args, **kwargs)

    with patch("socket.getaddrinfo", side_effect=delayed_resolve):
        _snapshot_worker(connection, url, timeout)


class RemoteDialTests(WorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.home = self.work / "home"
        self.data = (PROJECT_ROOT / "api/hive-hub/v1/dial-snapshot.json").read_bytes()
        self.snapshot = json.loads(self.data)
        self.envelope = self.snapshot["records"][0]["record"]
        self.query = self.envelope["chants"][0]["value"]
        self.requests: list[str] = []
        self.response_status = 200
        self.response_headers: dict[str, str] = {}
        self.extra_response_headers: list[tuple[str, str]] = []
        self.include_length = True
        self.dribble_headers = False
        self.header_delay = 0.0
        self.body_delay = 0.0
        self.dribble_started = threading.Event()
        self.stop_dribble = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append(self.path)
                if owner.dribble_headers:
                    owner.dribble_started.set()
                    try:
                        self.wfile.write(b"HTTP/1.1 200 OK\r\nX-Dribble: ")
                        end = time.monotonic() + 3
                        while time.monotonic() < end and not owner.stop_dribble.wait(0.02):
                            self.wfile.write(b"x")
                        self.wfile.write(b"\r\nContent-Length: 0\r\n\r\n")
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    return
                if owner.header_delay:
                    owner.stop_dribble.wait(owner.header_delay)
                self.send_response(owner.response_status)
                self.send_header("Content-Type", "application/json")
                if owner.include_length and "Content-Length" not in owner.response_headers:
                    self.send_header("Content-Length", str(len(owner.data)))
                for key, value in owner.response_headers.items():
                    self.send_header(key, value)
                for key, value in owner.extra_response_headers:
                    self.send_header(key, value)
                self.end_headers()
                if owner.body_delay:
                    owner.dribble_started.set()
                    owner.stop_dribble.wait(owner.body_delay)
                with suppress(BrokenPipeError, ConnectionResetError):
                    self.wfile.write(owner.data)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_port}/"
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self) -> None:
        self.stop_dribble.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def cli(self, *args: str, expected: int = 0) -> dict:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--home", str(self.home), *args])
        self.assertEqual(code, expected, stderr.getvalue() or stdout.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        if code == 0:
            self.assertEqual(stderr.getvalue(), "")
            return json.loads(stdout.getvalue())
        self.assertEqual(stdout.getvalue(), "")
        return json.loads(stderr.getvalue())

    def remote(self, *args: str, expected: int = 0) -> dict:
        return self.cli("dial", self.query, "--from", self.base, *args, expected=expected)

    def set_snapshot(self, snapshot: dict, *, rehash: bool = False) -> None:
        if rehash:
            for entry in snapshot["records"]:
                entry["ref"] = "sha256:" + hashlib.sha256(
                    canonical_bytes(entry["record"]) + b"\n"
                ).hexdigest()
        self.data = canonical_bytes(snapshot) + b"\n"

    def test_plan_pins_one_read_only_snapshot_and_writes_nothing(self) -> None:
        plan = self.remote()
        self.assertEqual(self.requests, ["/api/hive-hub/v1/dial-snapshot.json"])
        again = self.remote()
        self.assertEqual(plan, again)
        body = {key: value for key, value in plan.items() if key != "plan_id"}
        self.assertEqual(plan["plan_id"], content_address(body))
        self.assertEqual(plan["fetches"], [{
            "url": self.base + "api/hive-hub/v1/dial-snapshot.json",
            "expected_sha256": hashlib.sha256(self.data).hexdigest(),
            "max_bytes": MAX_JSON_BYTES,
        }])
        self.assertEqual(plan["redirects"], "forbidden")
        self.assertFalse(plan["adapter_execution"])
        self.assertFalse(self.home.exists())
        self.assertEqual(self.requests, ["/api/hive-hub/v1/dial-snapshot.json"] * 2)

    def test_changed_snapshot_requires_replanning_before_registration(self) -> None:
        self.query = self.envelope["coreRecord"]["urls"][0]
        plan = self.remote()
        result = self.remote("--apply", plan["plan_id"])
        self.assertEqual(result["record"], self.envelope["coreRecord"])
        before = {str(path): path.read_bytes() for path in files_under(self.home)}
        alternate = copy.deepcopy(self.envelope)
        fields = {
            key: value for key, value in alternate["coreRecord"].items()
            if key not in {"kind", "schema_version", "id"}
        }
        fields["name"] += " replacement"
        core = DialRecord.create(**fields)
        alternate.update(
            coreRecord=core.to_dict(), dialId=core.dial_id, displayName=core.name,
            recordId="replacement-record", aliases=["replacement-record"],
            chants=[{"role": "candidate-locator-only", "value": derive_chant(core.dial_id)}],
        )
        self.set_snapshot({"kind": "published-dial-snapshot", "schema_version": 1,
                           "records": [{"record": alternate}]}, rehash=True)
        error = self.remote("--apply", plan["plan_id"], expected=2)
        self.assertEqual(error["error"]["code"], "validation-error")
        self.assertIn("re-plan", error["error"]["message"])
        self.assertEqual(
            {str(path): path.read_bytes() for path in files_under(self.home)}, before
        )
        fresh = self.remote()
        self.assertNotEqual(fresh["plan_id"], plan["plan_id"])
        self.assertEqual(
            fresh["fetches"][0]["expected_sha256"], hashlib.sha256(self.data).hexdigest()
        )
        self.assertEqual(self.remote("--apply", fresh["plan_id"])["status"], "ambiguous")

    def test_header_dribble_cannot_extend_the_total_fetch_deadline(self) -> None:
        children = {process.pid for process in multiprocessing.active_children()}
        with patch("hive_hub.store.HTTP_FETCH_TIMEOUT_SECONDS", 1):
            plan = self.remote()
            self.dribble_headers = True
            started = time.monotonic()
            try:
                error = self.remote("--apply", plan["plan_id"], expected=2)
            finally:
                elapsed = time.monotonic() - started
                self.stop_dribble.set()
        self.assertTrue(self.dribble_started.is_set())
        self.assertEqual(error["error"]["code"], "fetch-error")
        self.assertFalse(self.home.exists())
        self.assertLess(elapsed, 1.75, f"one-second deadline took {elapsed:.3f}s")
        self.assertEqual(
            {process.pid for process in multiprocessing.active_children()}, children
        )

    def test_dns_is_inside_the_deadline_and_its_worker_is_reaped(self) -> None:
        children = {process.pid for process in multiprocessing.active_children()}
        with (
            patch("hive_hub.store.HTTP_FETCH_TIMEOUT_SECONDS", 1),
            patch("hive_hub._http_fetch._snapshot_worker", new=_slow_dns_worker),
        ):
            started = time.monotonic()
            error = self.remote(expected=2)
            elapsed = time.monotonic() - started
        self.assertEqual(error["error"]["code"], "fetch-error")
        self.assertLess(elapsed, 1.75)
        self.assertFalse(self.home.exists())
        self.assertEqual(self.requests, [])
        self.assertEqual(
            {process.pid for process in multiprocessing.active_children()}, children
        )

    def test_body_read_cannot_reset_the_header_phase_deadline(self) -> None:
        with patch("hive_hub.store.HTTP_FETCH_TIMEOUT_SECONDS", 1):
            plan = self.remote()
            self.header_delay = 0.5
            self.body_delay = 2.0
            started = time.monotonic()
            try:
                error = self.remote("--apply", plan["plan_id"], expected=2)
            finally:
                elapsed = time.monotonic() - started
                self.stop_dribble.set()
        self.assertTrue(self.dribble_started.is_set())
        self.assertEqual(error["error"]["code"], "fetch-error")
        self.assertLess(elapsed, 1.75)
        self.assertFalse(self.home.exists())

    def test_all_content_encoding_headers_must_be_identity(self) -> None:
        plan = self.remote()
        for values in (
            ["identity", "gzip"], ["gzip", "identity"], ["identity, gzip"],
        ):
            with self.subTest(values=values):
                self.extra_response_headers = [("Content-Encoding", value) for value in values]
                error = self.remote("--apply", plan["plan_id"], expected=2)
                self.assertEqual(error["error"]["code"], "fetch-error")
                self.assertFalse(self.home.exists())

    def test_duplicate_content_lengths_are_refused(self) -> None:
        plan = self.remote()
        self.extra_response_headers = [("Content-Length", str(len(self.data) + 1))]
        error = self.remote("--apply", plan["plan_id"], expected=2)
        self.assertEqual(error["error"]["code"], "fetch-error")
        self.assertFalse(self.home.exists())

    def test_snapshot_pin_binds_raw_bytes_including_whitespace(self) -> None:
        plan = self.remote()
        self.data += b"\n"
        error = self.remote("--apply", plan["plan_id"], expected=2)
        self.assertEqual(error["error"]["code"], "validation-error")
        self.assertIn("re-plan", error["error"]["message"])
        self.assertFalse(self.home.exists())
        fresh = self.remote()
        self.assertEqual(self.remote("--apply", fresh["plan_id"])["status"], "resolved")

    def test_wrong_or_retargeted_approval_never_registers(self) -> None:
        plan = self.remote()
        for approval in ("bad", "urn:hivehub:sha256:" + "0" * 64):
            with self.subTest(approval=approval):
                self.requests.clear()
                error = self.remote("--apply", approval, expected=2)
                self.assertIn("does not match", error["error"]["message"])
                self.assertEqual(
                    self.requests,
                    [] if approval == "bad" else ["/api/hive-hub/v1/dial-snapshot.json"],
                )
        self.requests.clear()
        self.cli(
            "dial", self.envelope["dialId"], "--from", self.base,
            "--apply", plan["plan_id"], expected=2,
        )
        self.cli(
            "dial", self.query, "--from", self.base + "different/",
            "--apply", plan["plan_id"], expected=2,
        )
        self.assertFalse(self.home.exists())
        self.assertEqual(self.requests, [
            "/api/hive-hub/v1/dial-snapshot.json",
            "/different/api/hive-hub/v1/dial-snapshot.json",
        ])

    def test_approval_pins_a_known_full_record_digest(self) -> None:
        plan = self.cli("dial", self.envelope["dialId"], "--from", self.base)
        self.assertEqual(plan["expected_record_id"], self.envelope["coreRecord"]["id"])
        result = self.cli(
            "dial", self.envelope["dialId"], "--from", self.base,
            "--apply", plan["plan_id"],
        )
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["record"]["id"], plan["expected_record_id"])

    def test_approval_is_bound_to_the_destination_home(self) -> None:
        plan = self.remote()
        first_home = self.home
        self.home = self.work / "different-home"
        self.remote("--apply", plan["plan_id"], expected=2)
        self.assertEqual(self.requests, ["/api/hive-hub/v1/dial-snapshot.json"] * 2)
        self.assertFalse(first_home.exists())
        self.assertFalse(self.home.exists())

    def test_happy_path_registers_verified_dependencies_and_resolves_offline(self) -> None:
        plan = self.remote()
        result = self.remote("--apply", plan["plan_id"])
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["record"], self.envelope["coreRecord"])
        self.assertEqual(self.requests, ["/api/hive-hub/v1/dial-snapshot.json"] * 2)
        self.assertFalse((self.home / "books/private").exists())
        hub = HiveHub(self.home)
        with patch(
            "hive_hub.store._fetch_public_snapshot", side_effect=AssertionError("implicit fetch")
        ):
            for query in (
                self.query.upper().replace("-", " "), self.envelope["dialId"],
                self.envelope["coreRecord"]["id"], self.envelope["coreRecord"]["urls"][0],
            ):
                self.assertEqual(hub.dial(query, scope="public").record.id, result["record"]["id"])
            index = hub.build_public_index(persist=False)
            self.assertIn(self.query, [entry["candidate"] for entry in index["chant_candidates"]])
            status = hub.status()
            self.assertEqual(status["counts"]["public_records"], 1)
        files_before = {str(path): path.read_bytes() for path in files_under(self.home)}
        self.assertEqual(self.remote("--apply", plan["plan_id"]), result)
        self.assertEqual(
            {str(path): path.read_bytes() for path in files_under(self.home)}, files_before
        )

    def test_tampered_web_content_address_is_refused_before_writes(self) -> None:
        self.snapshot["records"][0]["record"]["summary"] = "tampered"
        self.set_snapshot(self.snapshot)
        plan = self.remote()
        error = self.remote("--apply", plan["plan_id"], expected=2)
        self.assertIn("content address mismatch", error["error"]["message"])
        self.assertFalse(self.home.exists())

    def test_rehashed_envelope_cannot_hide_a_tampered_core_identity(self) -> None:
        self.envelope["coreRecord"]["id"] = "urn:hivehub:sha256:" + "0" * 64
        self.set_snapshot(self.snapshot, rehash=True)
        plan = self.remote()
        error = self.remote("--apply", plan["plan_id"], expected=2)
        self.assertIn("canonical identity body", error["error"]["message"])
        self.assertFalse(self.home.exists())

    def test_rehashed_envelope_cannot_replace_dial_id_chant_or_contracts(self) -> None:
        for field in ("dialId", "chants", "coreContracts"):
            snapshot = copy.deepcopy(self.snapshot)
            envelope = snapshot["records"][0]["record"]
            if field == "dialId":
                envelope[field] = "dial:sha256:" + "0" * 64
            elif field == "chants":
                envelope[field][0]["value"] = derive_chant("dial:sha256:" + "0" * 64)
            else:
                envelope[field]["adapter"]["name"] = "substituted"
            with self.subTest(field=field):
                self.set_snapshot(snapshot, rehash=True)
                plan = self.remote()
                self.remote("--apply", plan["plan_id"], expected=2)
                self.assertFalse(self.home.exists())

    def test_redirects_including_different_hosts_are_never_followed(self) -> None:
        plan = self.remote()
        self.data = b""
        for status in (301, 302, 303, 307, 308):
            for target in (
                self.base + "unapproved",
                f"http://localhost:{self.server.server_port}/unapproved",
            ):
                with self.subTest(status=status, target=target):
                    self.response_status = status
                    self.response_headers = {"Location": target}
                    self.requests.clear()
                    error = self.remote("--apply", plan["plan_id"], expected=2)
                    self.assertEqual(error["error"]["code"], "fetch-error")
                    self.assertEqual(self.requests, ["/api/hive-hub/v1/dial-snapshot.json"])
                    self.assertFalse(self.home.exists())

    def test_unknown_duplicate_float_and_oversized_json_stay_rejected(self) -> None:
        plan = self.remote()
        unknown = copy.deepcopy(self.snapshot)
        unknown["records"][0]["record"]["coreRecord"]["unrecognized"] = True
        self.set_snapshot(unknown, rehash=True)
        payloads = [
            self.data,
            b'{"kind":"published-dial-snapshot","schema_version":1,"records":[],"records":[]}',
            b'{"kind":"published-dial-snapshot","schema_version":1.0,"records":[]}',
            b'{"kind":"published-dial-snapshot","schema_version":true,"records":[]}',
            b"[" * 2000 + b"]" * 2000,
            b" " * (MAX_JSON_BYTES + 1),
        ]
        for data in payloads:
            with self.subTest(length=len(data)):
                self.data = data
                if len(data) <= MAX_JSON_BYTES:
                    plan = self.remote()
                self.remote("--apply", plan["plan_id"], expected=2)
                self.assertFalse(self.home.exists())

    def test_streamed_bytes_are_capped_without_content_length(self) -> None:
        plan = self.remote()
        self.include_length = False
        self.data = b" " * (MAX_JSON_BYTES + 1)
        error = self.remote("--apply", plan["plan_id"], expected=2)
        self.assertEqual(error["error"]["code"], "limit-exceeded")
        self.assertFalse(self.home.exists())

    def test_large_individual_envelope_is_rejected_below_snapshot_cap(self) -> None:
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["records"][0]["record"]["extra"] = [
            "x" * (MAX_RECORD_BYTES // 4) for _ in range(5)
        ]
        self.data = canonical_bytes(snapshot)
        plan = self.remote()
        error = self.remote("--apply", plan["plan_id"], expected=2)
        self.assertEqual(error["error"]["code"], "limit-exceeded")
        self.assertFalse(self.home.exists())

    def test_encoded_or_incomplete_responses_fail_closed(self) -> None:
        plan = self.remote()
        for headers in (
            {"Content-Encoding": "gzip"},
            {"Content-Length": "invalid"},
            {"Content-Length": str(len(self.data) + 1)},
        ):
            with self.subTest(headers=headers):
                self.response_headers = headers
                error = self.remote("--apply", plan["plan_id"], expected=2)
                self.assertEqual(error["error"]["code"], "fetch-error")
                self.assertFalse(self.home.exists())

    def test_missing_and_unauthorized_origins_have_identical_failures(self) -> None:
        plan = self.remote()
        self.data = b""
        errors = []
        for status in (401, 403, 404):
            self.response_status = status
            errors.append(self.remote("--apply", plan["plan_id"], expected=2))
        self.assertEqual(errors[0], errors[1])
        self.assertEqual(errors[1], errors[2])
        self.assertFalse(self.home.exists())

    def test_no_match_performs_no_registration(self) -> None:
        self.query = "dial:sha256:" + "0" * 64
        plan = self.remote()
        self.assertEqual(self.remote("--apply", plan["plan_id"])["status"], "unreachable")
        self.assertFalse(self.home.exists())

    def test_colliding_url_candidates_remain_ambiguous(self) -> None:
        alternate = copy.deepcopy(self.envelope)
        fields = {
            key: value for key, value in alternate["coreRecord"].items()
            if key not in {"kind", "schema_version", "id"}
        }
        fields["name"] += " alternate"
        core = DialRecord.create(**fields)
        alternate.update(
            coreRecord=core.to_dict(), dialId=core.dial_id, displayName=core.name,
            chants=[{"role": "candidate-locator-only", "value": derive_chant(core.dial_id)}],
        )
        self.snapshot["records"] = [self.snapshot["records"][0], {"record": alternate}]
        self.set_snapshot(self.snapshot, rehash=True)
        self.query = core.urls[0]
        plan = self.remote()
        result = self.remote("--apply", plan["plan_id"])
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["record"])
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(len(HiveHub(self.home).public_book.records()), 2)

    def test_legacy_labels_cannot_impersonate_a_published_derived_chant(self) -> None:
        original_chant = self.query
        for index, label in enumerate((original_chant, "acme bank support desk")):
            for query_kind in ("id", "url"):
                with self.subTest(label=label, query_kind=query_kind):
                    self.home = self.work / f"squatting-{index}-{query_kind}"
                    alternate = copy.deepcopy(self.envelope)
                    fields = {
                        key: value for key, value in alternate["coreRecord"].items()
                        if key not in {"kind", "schema_version", "id"}
                    }
                    fields["chants"] = [label]
                    core = DialRecord.create(**fields)
                    self.assertNotEqual(derive_chant(core.dial_id), label)
                    alternate.update(
                        coreRecord=core.to_dict(), dialId=core.dial_id,
                        chants=[{"role": "candidate-locator-only",
                                 "value": derive_chant(core.dial_id)}],
                    )
                    self.set_snapshot(
                        {"kind": "published-dial-snapshot", "schema_version": 1,
                         "records": [{"record": alternate}]}, rehash=True,
                    )
                    self.query = core.dial_id if query_kind == "id" else core.urls[0]
                    plan = self.remote()
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with redirect_stdout(stdout), redirect_stderr(stderr):
                        code = main([
                            "--home", str(self.home), "dial", self.query, "--from", self.base,
                            "--apply", plan["plan_id"],
                        ])
                    created_home = self.home.exists()
                    offline = HiveHub(self.home).dial(label, scope="public")
                    self.assertEqual(offline.status, "unreachable", "squatting survived offline")
                    self.assertEqual(code, 2, stdout.getvalue() or stderr.getvalue())
                    self.assertFalse(created_home)

    def test_import_urls_must_match_the_published_locator(self) -> None:
        for index, urls in enumerate((
            ["https://unrelated.invalid/claimed-hive"],
            self.envelope["coreRecord"]["urls"][:-1],
        )):
            with self.subTest(urls=urls):
                self.home = self.work / f"url-mismatch-{index}"
                alternate = copy.deepcopy(self.envelope)
                fields = {
                    key: value for key, value in alternate["coreRecord"].items()
                    if key not in {"kind", "schema_version", "id"}
                }
                fields["urls"] = urls
                core = DialRecord.create(**fields)
                alternate.update(
                    coreRecord=core.to_dict(), dialId=core.dial_id,
                    chants=[{"role": "candidate-locator-only",
                             "value": derive_chant(core.dial_id)}],
                )
                self.set_snapshot(
                    {"kind": "published-dial-snapshot", "schema_version": 1,
                     "records": [{"record": alternate}]}, rehash=True,
                )
                self.query = core.dial_id
                plan = self.remote()
                self.remote("--apply", plan["plan_id"], expected=2)
                self.assertFalse(self.home.exists())

    def test_invalid_chant_candidate_blocks_the_entire_url_import(self) -> None:
        alternate = copy.deepcopy(self.envelope)
        fields = {
            key: value for key, value in alternate["coreRecord"].items()
            if key not in {"kind", "schema_version", "id"}
        }
        fields["chants"] = [self.query]
        core = DialRecord.create(**fields)
        alternate.update(
            coreRecord=core.to_dict(), dialId=core.dial_id,
            chants=[{"role": "candidate-locator-only", "value": derive_chant(core.dial_id)}],
        )
        self.set_snapshot(
            {"kind": "published-dial-snapshot", "schema_version": 1,
             "records": [self.snapshot["records"][0], {"record": alternate}]},
            rehash=True,
        )
        self.query = core.urls[0]
        plan = self.remote()
        self.remote("--apply", plan["plan_id"], expected=2)
        self.assertFalse(self.home.exists())

    def test_published_presentation_fields_follow_schema_rules(self) -> None:
        cases = [
            ("recordId", {}, None), ("recordId", "", None),
            ("aliases", ["invalid alias"], None), ("aliases", [], None),
            ("aliases", {"label": "object"}, None),
            ("protocolFingerprint", 7, None),
            ("protocolFingerprint", "sha256:" + "0" * 64, None),
            ("chantProtocolFingerprint", "sha256:" + "0" * 64, None),
            ("$schema", "file:///etc/passwd", None),
        ]
        for name in ("protocol", "learningBundle", "conformance", "adapter", "chantProtocol"):
            for field, invalid in (
                ("path", "../../etc/passwd"), ("path", "/absolute/file"),
                ("path", r"relative\file.json"), ("path", "%2e%2e/secret"),
                ("url", "file:///etc/passwd"), ("url", "http://example.test/plaintext"),
                ("url", "https://example.test/unrelated.json"), ("ref", 7),
            ):
                cases.append((name, invalid, field))
        for index, (name, invalid, nested) in enumerate(cases):
            with self.subTest(name=name, nested=nested, invalid=invalid):
                self.home = self.work / f"invalid-presentation-{index}"
                alternate = copy.deepcopy(self.envelope)
                if nested:
                    alternate[name][nested] = invalid
                else:
                    alternate[name] = invalid
                self.set_snapshot(
                    {"kind": "published-dial-snapshot", "schema_version": 1,
                     "records": [{"record": alternate}]}, rehash=True,
                )
                self.query = alternate["dialId"]
                plan = self.remote()
                self.remote("--apply", plan["plan_id"], expected=2)
                self.assertFalse(self.home.exists())

    def test_registration_failure_rolls_back_only_new_files(self) -> None:
        plan = self.remote()
        original = SafeFilesystem.apply_write

        def fail_record(filesystem: SafeFilesystem, write: WritePlan) -> bool:
            if write.relative_path.startswith("books/public/records/"):
                raise OSError("fixture write failure")
            return original(filesystem, write)

        with patch.object(SafeFilesystem, "apply_write", new=fail_record):
            self.remote("--apply", plan["plan_id"], expected=3)
        self.assertEqual(list((self.home / "registry").rglob("*.json")), [])
        self.assertEqual(list((self.home / "books").rglob("*.json")), [])

    def test_rollback_preserves_preexisting_shared_dependencies(self) -> None:
        published = PublishedRecord.from_dict(self.envelope)
        hub = HiveHub(self.home)
        hub.learn_protocol(published.declaration, published.bundle)
        before = {str(path): path.read_bytes() for path in files_under(self.home)}
        plan = self.remote()
        original = SafeFilesystem.apply_write

        def fail_record(filesystem: SafeFilesystem, write: WritePlan) -> bool:
            if write.relative_path.startswith("books/public/records/"):
                raise OSError("fixture write failure")
            return original(filesystem, write)

        with patch.object(SafeFilesystem, "apply_write", new=fail_record):
            self.remote("--apply", plan["plan_id"], expected=3)
        after = {
            str(path): path.read_bytes()
            for path in files_under(self.home) if path.suffix != ".lock"
        }
        self.assertEqual(after, before)

    def test_downloaded_code_is_stored_as_data_and_never_executed(self) -> None:
        published = PublishedRecord.from_dict(self.envelope)
        code = "raise AssertionError('downloaded code must remain inert')"
        bundle = LearningBundle.create(
            protocol_fingerprint=published.declaration.fingerprint,
            bundle_version=published.bundle.bundle_version,
            summary=published.bundle.summary,
            conformance_contract=published.bundle.conformance_contract,
            artifacts=[
                *published.bundle.artifacts,
                LearningArtifact.create(
                    name="untrusted.py", media_type="text/x-python", content=code
                ),
            ],
        )
        fields = {
            key: value for key, value in published.record.to_dict().items()
            if key not in {"kind", "schema_version", "id"}
        }
        fields["learning_bundle_address"] = bundle.address
        record = DialRecord.create(**fields)
        self.envelope["coreRecord"] = record.to_dict()
        self.envelope["coreContracts"]["learningBundle"] = bundle.to_dict()
        self.envelope["dialId"] = record.dial_id
        self.envelope["chants"][0]["value"] = derive_chant(record.dial_id)
        self.set_snapshot(self.snapshot, rehash=True)
        self.query = record.dial_id
        plan = self.remote()
        self.assertEqual(self.remote("--apply", plan["plan_id"])["status"], "resolved")
        stored = HiveHub(self.home).registry.get_bundle(bundle.address)
        self.assertEqual(stored.artifacts[-1].content, code)

    def test_existing_different_bytes_and_symlinks_are_not_overwritten(self) -> None:
        record = project_published_record(self.envelope)
        path = self.home / "books/public/records" / (record.id.rsplit(":", 1)[1] + ".json")
        path.parent.mkdir(parents=True)
        path.write_bytes(b"do not replace")
        plan = self.remote()
        error = self.remote("--apply", plan["plan_id"], expected=2)
        self.assertEqual(error["error"]["code"], "conflict")
        self.assertEqual(path.read_bytes(), b"do not replace")
        self.assertEqual(list((self.home / "registry").rglob("*.json")), [])
        path.unlink()
        target = self.work / "outside"
        target.write_bytes(b"outside")
        path.symlink_to(target)
        error = self.remote("--apply", plan["plan_id"], expected=2)
        self.assertEqual(error["error"]["code"], "unsafe-path")
        self.assertEqual(target.read_bytes(), b"outside")

    def test_private_scopes_and_unapproved_transports_never_fetch(self) -> None:
        for extra in (
            ["--scope", "private"], ["--scope", "local"],
            ["--acl-authorized"], ["--qr-fragment-stdin"],
        ):
            with self.subTest(extra=extra):
                self.remote(*extra, expected=2)
        self.cli("dial", self.query, "--apply", "anything", expected=2)
        for base in (
            "file:///tmp/", "http://example.test/", "https://user:password@example.test/",
            "https://example.test/?token=sensitive", "https://example.test/#fragment",
            "https://example.test/../", "https://example.test/%2e%2e/",
            "https://example.test:invalid/",
        ):
            with self.subTest(base=base):
                self.cli("dial", self.query, "--from", base, expected=2)
        self.assertEqual(self.requests, [])
        self.assertFalse(self.home.exists())

    def test_every_built_record_has_a_complete_inert_registration_stack(self) -> None:
        for entry in self.snapshot["records"]:
            with self.subTest(record=entry["record"]["recordId"]):
                published = PublishedRecord.from_dict(entry["record"])
                self.assertEqual(published.record.chants, ())
                self.assertEqual(published.adapter.effect_kinds, ())
                self.assertEqual(published.adapter.operations, ("inspect",))

    def test_every_built_chant_can_be_imported_and_indexed(self) -> None:
        for entry in self.snapshot["records"]:
            with self.subTest(record=entry["record"]["recordId"]):
                self.query = entry["record"]["chants"][0]["value"]
                plan = self.remote()
                result = self.remote("--apply", plan["plan_id"])
                self.assertEqual(result["status"], "resolved")
                self.assertEqual(result["record"], entry["record"]["coreRecord"])
        index = HiveHub(self.home).build_public_index(persist=False)
        self.assertEqual(len(index["records"]), len(self.snapshot["records"]))
