from __future__ import annotations

import unittest

from hive_hub.canonical import address_digest, canonical_bytes, content_address, loads_json
from hive_hub.chant import derive_chant
from hive_hub.contracts import DialRecord
from hive_hub.limits import MAX_RECORD_BYTES
from hive_hub.published import PublishedRecord

from .helpers import PROJECT_ROOT


class PublishedRecordConformanceTests(unittest.TestCase):
    """Check the actual public build, independently of the builder's projection."""

    def test_every_published_record_has_one_core_identity_and_derived_chant(self) -> None:
        dialbook = loads_json(
            (PROJECT_ROOT / "api/hive-hub/v1/dialbook.json").read_bytes()
        )
        self.assertIsInstance(dialbook, dict)
        descriptors = dialbook["records"]
        manifest = loads_json((PROJECT_ROOT / "public-manifest.json").read_bytes())
        expected_count = sum(entry["kind"] == "record" for entry in manifest["entries"])
        self.assertGreater(expected_count, 0, "the oracle must not pass an empty build")
        self.assertEqual(len(descriptors), expected_count)

        for descriptor in descriptors:
            with self.subTest(record=descriptor["path"]):
                raw = (PROJECT_ROOT / descriptor["path"]).read_bytes()
                envelope = loads_json(raw, max_bytes=MAX_RECORD_BYTES)
                self.assertIsInstance(
                    envelope.get("coreRecord"), dict, "published record has no coreRecord"
                )
                record = DialRecord.from_dict(envelope["coreRecord"])
                self.assertEqual(PublishedRecord.from_dict(envelope).record, record)
                self.assertEqual(envelope["coreRecord"], record.to_dict())
                body = record._body(
                    name=record.name,
                    description=record.description,
                    visibility=record.visibility,
                    protocol_fingerprint=record.protocol_fingerprint,
                    learning_bundle_address=record.learning_bundle_address,
                    adapter_registration_address=record.adapter_registration_address,
                    urls=record.urls,
                    chants=record.chants,
                )
                self.assertEqual(record.id, content_address(body))
                dial_id = "dial:sha256:" + address_digest(record.id)
                self.assertEqual(envelope["dialId"], dial_id)
                self.assertEqual(
                    envelope["chants"],
                    [{"role": "candidate-locator-only", "value": derive_chant(dial_id)}],
                )
                self.assertEqual(
                    descriptor["ref"],
                    "sha256:" + address_digest(content_address(raw, raw=True)),
                )
                self.assertEqual(raw, canonical_bytes(envelope) + b"\n")

    def test_record_store_contains_only_active_records_and_exact_archived_bytes(self) -> None:
        dialbook = loads_json((PROJECT_ROOT / "api/hive-hub/v1/dialbook.json").read_bytes())
        active = {PROJECT_ROOT / descriptor["path"] for descriptor in dialbook["records"]}
        paths = set((PROJECT_ROOT / "api/hive-hub/v1/records/sha256").glob("*/*.json"))
        manifest = loads_json((PROJECT_ROOT / "public-manifest.json").read_bytes())
        archived = set()
        for entry in manifest["entries"]:
            if entry["kind"] != "historical-object":
                continue
            raw = (PROJECT_ROOT / "public-src" / entry["path"]).read_bytes()
            document = loads_json(raw)
            if document.get("kind") != "dial-record":
                continue
            self.assertEqual(address_digest(content_address(raw, raw=True)), entry["sha256"])
            matching = [path for path in paths if path.stem == entry["sha256"]]
            self.assertEqual(len(matching), 1, "archived record disappeared or was duplicated")
            self.assertEqual(matching[0].read_bytes(), raw)
            archived.add(matching[0])
        self.assertEqual(paths, active | archived, "an emitted record escaped the oracle")


if __name__ == "__main__":
    unittest.main()
