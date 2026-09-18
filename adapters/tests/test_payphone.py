from __future__ import annotations

import unittest
from unittest.mock import patch

from adapters.contracts import (
    AccessOutcome,
    AdapterRefusal,
    PrivateAccessMode,
)
from adapters.payphone import DoorObservation, PayphoneAdapter, door_from_rappid
from adapters.tests.support import fixture


class PayphoneTests(unittest.TestCase):
    def test_new_local_door_ref_vectors_are_exact(self) -> None:
        vectors = fixture("payphone_vectors.json")
        assert isinstance(vectors, dict)
        for vector in vectors["vectors"]:
            self.assertEqual(
                door_from_rappid(vector["rappid"]).as_dict(),
                vector["door_ref"],
            )

    def test_door_derivation_is_pure(self) -> None:
        vector = fixture("payphone_vectors.json")
        assert isinstance(vector, dict)
        rappid = vector["vectors"][0]["rappid"]
        with (
            patch("builtins.open") as opened,
            patch("subprocess.run") as ran,
            patch("urllib.request.urlopen") as fetched,
            patch("time.time") as clock,
        ):
            first = door_from_rappid(rappid)
            second = door_from_rappid(rappid)
        self.assertEqual(first, second)
        opened.assert_not_called()
        ran.assert_not_called()
        fetched.assert_not_called()
        clock.assert_not_called()

    def test_connected_requires_reachable_acl_and_full_rappid(self) -> None:
        vectors = fixture("payphone_vectors.json")
        assert isinstance(vectors, dict)
        rappid = vectors["vectors"][0]["rappid"]
        door = door_from_rappid(rappid)
        adapter = PayphoneAdapter()
        connected = adapter.evaluate(
            rappid,
            DoorObservation(
                access=AccessOutcome.REACHABLE,
                presented_rappid=rappid,
                peer_id=door.tethers.webrtc.peer_id,
                label=door.tethers.issues.label,
            ),
        )
        self.assertEqual(connected.outcome, "connected")
        missing_identity = adapter.evaluate(
            rappid,
            DoorObservation(
                access=AccessOutcome.REACHABLE,
                presented_rappid=None,
            ),
        )
        self.assertEqual(missing_identity.outcome, "unreachable")

    def test_absent_and_unauthorized_collapse_to_same_result(self) -> None:
        vectors = fixture("payphone_vectors.json")
        assert isinstance(vectors, dict)
        rappid = vectors["vectors"][0]["rappid"]
        adapter = PayphoneAdapter()
        absent = adapter.evaluate(
            rappid,
            DoorObservation(AccessOutcome.UNREACHABLE, None),
        )
        unauthorized = adapter.evaluate(
            rappid,
            DoorObservation(AccessOutcome.UNREACHABLE, rappid),
        )
        self.assertEqual(absent, unauthorized)
        self.assertEqual(absent.outcome, "unreachable")
        self.assertNotIn("no-answer", vectors["outcomes"])

    def test_acl_plus_qr_is_after_acl_and_contains_no_credential(self) -> None:
        vectors = fixture("payphone_vectors.json")
        assert isinstance(vectors, dict)
        rappid = vectors["vectors"][0]["rappid"]
        adapter = PayphoneAdapter()
        refused = adapter.evaluate(
            rappid,
            DoorObservation(
                access=AccessOutcome.REACHABLE,
                presented_rappid=rappid,
                qr_verified=False,
            ),
            access_mode=PrivateAccessMode.ACL_PLUS_QR,
        )
        accepted = adapter.evaluate(
            rappid,
            DoorObservation(
                access=AccessOutcome.REACHABLE,
                presented_rappid=rappid,
                qr_verified=True,
            ),
            access_mode=PrivateAccessMode.ACL_PLUS_QR,
        )
        self.assertEqual(refused.outcome, "unreachable")
        self.assertEqual(accepted.outcome, "connected")

    def test_truncated_peer_and_label_collisions_refuse_without_full_rappid(
        self,
    ) -> None:
        vectors = fixture("payphone_vectors.json")
        assert isinstance(vectors, dict)
        collision = vectors["truncated_collision"]
        adapter = PayphoneAdapter()
        for reference in (collision["peer_id"], collision["label"]):
            with (
                self.subTest(reference=reference),
                self.assertRaises(AdapterRefusal) as refusal,
            ):
                adapter.resolve_truncated(
                    reference,
                    collision["rappids"],
                    full_rappid=None,
                )
            self.assertEqual(
                refusal.exception.code,
                "payphone-truncated-collision",
            )
            selected = adapter.resolve_truncated(
                reference,
                collision["rappids"],
                full_rappid=collision["rappids"][1],
            )
            self.assertEqual(selected.rappid, collision["rappids"][1])


if __name__ == "__main__":
    unittest.main()
