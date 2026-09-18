from __future__ import annotations

import hashlib
import unittest

from adapters.contracts import AdapterRefusal
from adapters.rappid import (
    CHANT_WORDS,
    RAPPID_VOCABULARY_SHA256,
    ChantCandidate,
    ChantCandidateResolver,
    RappidChantAdapter,
    parse_rappid,
)
from adapters.tests.support import fixture


class _CollisionDeriver:
    def __init__(self, chant: str) -> None:
        self._chant = chant

    def chant_for_rappid(self, _rappid: str) -> str:
        return self._chant


class RappidChantTests(unittest.TestCase):
    def test_frozen_vocabulary_and_upstream_vectors_are_exact(self) -> None:
        vectors = fixture("rappid_vectors.json")
        assert isinstance(vectors, dict)
        self.assertEqual(len(CHANT_WORDS), 128)
        self.assertEqual(
            hashlib.sha256("\n".join(CHANT_WORDS).encode("utf-8")).hexdigest(),
            RAPPID_VOCABULARY_SHA256,
        )
        self.assertEqual(vectors["vocabulary_sha256"], RAPPID_VOCABULARY_SHA256)
        adapter = RappidChantAdapter()
        for vector in vectors["vectors"]:
            self.assertEqual(
                adapter.chant_for_rappid(vector["rappid"]),
                vector["chant"],
            )
            human = vector["chant"].replace("-", " ").upper()
            self.assertEqual(adapter.normalize(human), vector["chant"])

    def test_canonical_rappid_parser_is_strict(self) -> None:
        good = (
            "rappid:@owner/example:"
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )
        self.assertEqual(parse_rappid(good).canonical, good)
        bad = (
            "",
            good.upper(),
            good + " ",
            good.replace("owner", "owner_name"),
            good[:-32],
            "rappid:v2:twin:@owner/example:" + "a" * 32,
        )
        for value in bad:
            with self.subTest(value=value), self.assertRaises(AdapterRefusal):
                parse_rappid(value)
        with self.assertRaises(AdapterRefusal):
            RappidChantAdapter().normalize(
                "ember--hollow-quartz-tidal-vessel-marrow-lantern"
            )
        with self.assertRaises(AdapterRefusal):
            RappidChantAdapter().normalize(
                "ember hollow-quartz-tidal-vessel-marrow-lantern"
            )

    def test_collision_bucket_retains_every_full_candidate(self) -> None:
        vectors = fixture("rappid_vectors.json")
        assert isinstance(vectors, dict)
        collision = vectors["collision"]
        candidates = tuple(
            ChantCandidate(
                rappid=item["rappid"],
                source=item["source"],
                content_sha256=item["content_sha256"],
            )
            for item in collision["candidates"]
        )
        resolver = ChantCandidateResolver(_CollisionDeriver(collision["chant"]))
        resolution = resolver.resolve(
            collision["chant"].replace("-", " ").upper(),
            candidates,
        )
        self.assertEqual(resolution.outcome, "collision")
        self.assertEqual(
            [candidate.rappid for candidate in resolution.candidates],
            sorted(candidate.rappid for candidate in candidates),
        )
        with self.assertRaises(AdapterRefusal) as refusal:
            resolver.select(resolution, full_rappid=None)
        self.assertEqual(refusal.exception.code, "chant-collision")
        expected = candidates[1]
        selected = resolver.select(
            resolution,
            full_rappid=expected.rappid,
            content_sha256=expected.content_sha256,
        )
        self.assertEqual(selected, expected)


if __name__ == "__main__":
    unittest.main()
