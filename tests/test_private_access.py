from __future__ import annotations

from unittest.mock import patch

from hive_hub import (
    Principal,
    PrivateAccessPolicy,
    canonical_dumps,
    generate_qr_fragment,
    public_index_from_home,
    qr_commitment,
)
from hive_hub.filesystem import SafeFilesystem

from .helpers import FIXED_TIME, WorkspaceTestCase, files_under, make_record, make_stack


class PrivateAccessTests(WorkspaceTestCase):
    def test_acl_only_is_default_and_acl_is_always_required(self) -> None:
        stack = make_stack(self.work)
        record = make_record(
            stack,
            visibility="private",
            name="Private Firefly",
            url="https://firefly.invalid/private/default",
            chant="private default",
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
            chant="vault firefly",
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

    def test_absent_unauthorized_and_wrong_qr_are_identical_unreachable(self) -> None:
        stack = make_stack(self.work)
        record = make_record(
            stack,
            visibility="private",
            name="Hidden Firefly",
            url="https://firefly.invalid/private/hidden",
            chant="hidden firefly",
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
            chant="never project me",
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

        def guarded(
            filesystem: SafeFilesystem,
            relative_path: str,
            *,
            max_bytes: int,
        ) -> bytes:
            if "private" in filesystem.root.parts:
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
            chant="transient firefly",
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
