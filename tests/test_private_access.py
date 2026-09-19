from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from hive_hub import (
    Principal,
    PrivateAccessPolicy,
    canonical_dumps,
    generate_qr_fragment,
    public_index_from_home,
    qr_commitment,
)
from hive_hub.errors import LimitError, ValidationError
from hive_hub.filesystem import SafeFilesystem

from .helpers import (
    FIXED_TIME,
    PROJECT_ROOT,
    WorkspaceTestCase,
    files_under,
    make_record,
    make_stack,
)


class PrivateAccessTests(WorkspaceTestCase):
    def test_acl_only_is_default_and_acl_is_always_required(self) -> None:
        stack = make_stack(self.work)
        record = make_record(
            stack,
            visibility="private",
            name="Private Firefly",
            url="https://firefly.invalid/private/default",
        )
        result = stack.hub.register_private_record(record)
        self.assertIsNotNone(result["policy_address"])
        denied = stack.hub.dial(record.id, scope="private", acl_authorized=False)
        allowed = stack.hub.dial(record.id, scope="private", acl_authorized=True)
        self.assertEqual(denied.status, "unreachable")
        self.assertEqual(allowed.status, "resolved")
        policy = stack.hub.private_book.get_policy(record.id)
        self.assertEqual(policy.mode, "acl-only")
        self.assertIsNone(policy.qr_commitment)

    def test_acl_qr_binds_scope_and_epoch_and_uses_constant_time_compare(self) -> None:
        stack = make_stack(self.work)
        record = make_record(
            stack,
            visibility="private",
            name="Vault Firefly",
            url="https://firefly.invalid/private/vault",
        )
        fragment = generate_qr_fragment()
        policy = PrivateAccessPolicy.create(
            record_id=record.id,
            mode="acl+qr",
            scope="vault/read",
            epoch="2026-q3",
            qr_fragment=fragment,
        )
        stack.hub.register_private_record(record, policy=policy)
        self.assertNotEqual(
            policy.qr_commitment,
            qr_commitment(
                record_id=record.id,
                scope="vault/write",
                epoch="2026-q3",
                fragment=fragment,
            ),
        )
        other_record = make_record(
            stack,
            visibility="private",
            name="Other Vault Firefly",
            url="https://firefly.invalid/private/other-vault",
        )
        self.assertNotEqual(
            policy.qr_commitment,
            qr_commitment(
                record_id=other_record.id,
                scope="vault/read",
                epoch="2026-q3",
                fragment=fragment,
            ),
        )
        self.assertNotEqual(
            policy.qr_commitment,
            qr_commitment(
                record_id=record.id,
                scope="vault/read",
                epoch="2026-q4",
                fragment=fragment,
            ),
        )
        original = __import__("hmac").compare_digest
        with patch("hive_hub.contracts.hmac.compare_digest", wraps=original) as compare:
            allowed = stack.hub.dial(
                record.id,
                scope="private",
                acl_authorized=True,
                qr_fragment=fragment,
            )
            self.assertEqual(allowed.status, "resolved")
            self.assertTrue(compare.called)

    def test_qr_factor_requires_canonical_32_byte_base64url_entropy(self) -> None:
        stack = make_stack(self.work)
        record = make_record(
            stack,
            visibility="private",
            name="Strict Factor Firefly",
            url="https://firefly.invalid/private/strict-factor",
        )
        for weak in ("short", "A" * 42, "A" * 43 + "=", "B" * 43):
            with self.subTest(weak=weak), self.assertRaises((LimitError, ValidationError)):
                PrivateAccessPolicy.create(
                    record_id=record.id,
                    mode="acl+qr",
                    qr_fragment=weak,
                )

    def test_absent_unauthorized_and_wrong_qr_are_identical_unreachable(self) -> None:
        stack = make_stack(self.work)
        record = make_record(
            stack,
            visibility="private",
            name="Hidden Firefly",
            url="https://firefly.invalid/private/hidden",
        )
        fragment = generate_qr_fragment()
        policy = PrivateAccessPolicy.create(
            record_id=record.id,
            mode="acl+qr",
            scope="hidden/read",
            epoch="9",
            qr_fragment=fragment,
        )
        stack.hub.register_private_record(record, policy=policy)
        absent = stack.hub.dial(
            "does not exist",
            scope="private",
            acl_authorized=True,
            qr_fragment=fragment,
        ).to_dict()
        unauthorized = stack.hub.dial(
            record.id,
            scope="private",
            acl_authorized=False,
            qr_fragment=fragment,
        ).to_dict()
        wrong_factor = stack.hub.dial(
            record.id,
            scope="private",
            acl_authorized=True,
            qr_fragment=generate_qr_fragment(),
        ).to_dict()
        self.assertEqual(absent, unauthorized)
        self.assertEqual(absent, wrong_factor)
        self.assertEqual(absent["status"], "unreachable")

    def test_public_builder_never_reads_or_hashes_private_book(self) -> None:
        stack = make_stack(self.work)
        public = make_record(stack)
        private = make_record(
            stack,
            visibility="private",
            name="Never Project Me",
            url="https://firefly.invalid/private/never",
        )
        fragment = generate_qr_fragment()
        policy = PrivateAccessPolicy.create(
            record_id=private.id,
            mode="acl+qr",
            qr_fragment=fragment,
        )
        stack.hub.register_public_record(public)
        stack.hub.register_private_record(private, policy=policy)
        self.assertTrue((self.work / "books" / "public" / "records").is_dir())
        self.assertTrue((self.work / "books" / "private" / "records").is_dir())

        original = SafeFilesystem.read_bytes
        private_root = (self.work / "books" / "private").resolve()

        def guarded(
            filesystem: SafeFilesystem,
            relative_path: str,
            *,
            max_bytes: int,
        ) -> bytes:
            root = Path(filesystem.root).resolve()
            if root == private_root or private_root in root.parents:
                raise AssertionError("public builder touched private storage")
            return original(filesystem, relative_path, max_bytes=max_bytes)

        with patch.object(SafeFilesystem, "read_bytes", new=guarded):
            index = public_index_from_home(self.work, persist=False)
        serialized = canonical_dumps(index.to_dict())
        self.assertIn(public.name, serialized)
        self.assertNotIn(private.name, serialized)
        self.assertNotIn(policy.qr_commitment, serialized)
        self.assertNotIn(fragment, serialized)

    def test_qr_fragment_is_never_persisted_in_records_receipts_cards_or_state(self) -> None:
        stack = make_stack(self.work)
        record = make_record(
            stack,
            visibility="private",
            name="Transient Factor Firefly",
            url="https://firefly.invalid/private/transient",
        )
        fragment = generate_qr_fragment()
        policy = PrivateAccessPolicy.create(
            record_id=record.id,
            mode="acl+qr",
            qr_fragment=fragment,
        )
        stack.hub.register_private_record(record, policy=policy)
        card = stack.hub.create_join_card(
            principal=Principal.create(kind="human", identifier="person:ada"),
            locator=record.id,
            issued_at=FIXED_TIME,
        )
        result = stack.hub.bootstrap(
            card,
            apply=True,
            scope="private",
            acl_authorized=True,
            qr_fragment=fragment,
        )
        self.assertEqual(result.status, "applied")
        for path in files_under(self.work):
            self.assertNotIn(fragment.encode("ascii"), path.read_bytes(), str(path))
        self.assertTrue((self.work / "books" / "private").is_dir())

    def test_private_record_and_policy_registration_is_one_interprocess_transaction(
        self,
    ) -> None:
        stack = make_stack(self.work)
        record = make_record(
            stack,
            visibility="private",
            name="Concurrent Firefly",
            url="https://firefly.invalid/private/concurrent",
        )
        first_policy = PrivateAccessPolicy.create(
            record_id=record.id,
            mode="acl+qr",
            scope="concurrent/read",
            epoch="1",
            qr_fragment=generate_qr_fragment(),
        )
        second_policy = PrivateAccessPolicy.create(
            record_id=record.id,
            mode="acl+qr",
            scope="concurrent/read",
            epoch="2",
            qr_fragment=generate_qr_fragment(),
        )
        record_path = self.work / "concurrent-record.json"
        policy_path = self.work / "concurrent-policy.json"
        attempted_path = self.work / "worker-attempted"
        entered_path = self.work / "worker-entered-apply"
        result_path = self.work / "worker-result"
        record_path.write_text(json.dumps(record.to_dict()), encoding="utf-8")
        policy_path.write_text(json.dumps(second_policy.to_dict()), encoding="utf-8")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(PROJECT_ROOT / "src"), str(PROJECT_ROOT)]
        )
        worker = PROJECT_ROOT / "tests/fixtures/register_private_worker.py"
        private_book = stack.hub.private_book
        record_plan = private_book.record_plan(record)
        first_policy_plan = private_book.policy_plan(first_policy)
        process: subprocess.Popen[str] | None = None
        try:
            with private_book.registration_transaction(record.id):
                self.assertTrue(private_book.apply(record_plan))
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        str(worker),
                        str(self.work),
                        str(record_path),
                        str(policy_path),
                        str(attempted_path),
                        str(entered_path),
                        str(result_path),
                    ],
                    cwd=PROJECT_ROOT,
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                deadline = time.monotonic() + 10
                while not attempted_path.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(attempted_path.exists(), "worker never attempted registration")
                time.sleep(0.2)
                self.assertIsNone(process.poll(), "worker bypassed the record transaction lock")
                self.assertFalse(entered_path.exists())
                self.assertTrue(private_book.apply(first_policy_plan))
            assert process is not None
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
        self.assertEqual(result_path.read_text(encoding="utf-8"), "conflict\n")
        self.assertEqual(private_book.get(record.id), record)
        self.assertEqual(private_book.get_policy(record.id), first_policy)
