from __future__ import annotations

import unittest
from collections.abc import Mapping, Sequence
from dataclasses import asdict

from adapters.contracts import AccessOutcome, AdapterRefusal
from adapters.github import GitHubRepositoryAdapter, parse_github_address
from adapters.tests.support import fixture


class GitHubAdapterTests(unittest.TestCase):
    def test_parse_vectors_have_one_canonical_url(self) -> None:
        vectors = fixture("github_vectors.json")
        assert isinstance(vectors, dict)
        for vector in vectors["parse"]:
            parsed = parse_github_address(vector["input"])
            self.assertEqual(parsed.owner, vector["owner"])
            self.assertEqual(parsed.repository, vector["repository"])
            self.assertEqual(parsed.branch, vector["branch"])
            self.assertEqual(parsed.canonical_url, vector["canonical_url"])
            self.assertEqual(parsed.tree_url, vector["tree_url"])
            self.assertEqual(parsed.display, vector["display"])

    def test_invalid_addresses_fail_closed(self) -> None:
        vectors = fixture("github_vectors.json")
        assert isinstance(vectors, dict)
        for value in vectors["invalid"]:
            with self.subTest(value=value), self.assertRaises(AdapterRefusal):
                parse_github_address(value)

    def test_probe_uses_ambient_credentials_without_prompts_or_writes(self) -> None:
        calls: list[tuple[list[str], dict[str, str], float]] = []

        def runner(
            command: Sequence[str],
            environment: Mapping[str, str],
            timeout: float,
        ) -> int:
            calls.append((list(command), dict(environment), timeout))
            return 0

        token = "fixture-token-must-never-be-logged"
        adapter = GitHubRepositoryAdapter(runner=runner)
        result = adapter.probe(
            "fixture-org/example at main",
            environment={"GITHUB_TOKEN": token},
        )
        self.assertEqual(result.outcome, AccessOutcome.REACHABLE)
        self.assertEqual(len(calls), 1)
        command, environment, _ = calls[0]
        self.assertEqual(
            command[:4], ["git", "-c", "credential.interactive=never", "ls-remote"]
        )
        self.assertIn("--exit-code", command)
        self.assertIn("refs/heads/main", command)
        self.assertNotIn("push", command)
        self.assertNotIn("clone", command)
        self.assertNotIn("fetch", command)
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(environment["GCM_INTERACTIVE"], "Never")
        self.assertFalse(result.prompts_enabled)
        self.assertFalse(result.remote_writes)
        self.assertNotIn(token, repr(result))

    def test_absent_and_unauthorized_are_indistinguishable(self) -> None:
        address = "fixture-org/private-candidate at main"

        def result_for(return_code: int) -> dict[str, object]:
            adapter = GitHubRepositoryAdapter(
                runner=lambda _command, _environment, _timeout: return_code
            )
            return asdict(adapter.probe(address, environment={}))

        self.assertEqual(result_for(22), result_for(128))
        self.assertEqual(
            result_for(22)["outcome"],
            AccessOutcome.UNREACHABLE,
        )


if __name__ == "__main__":
    unittest.main()
