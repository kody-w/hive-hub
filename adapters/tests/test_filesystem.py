from __future__ import annotations

import unittest

from adapters.contracts import AccessOutcome
from adapters.filesystem import LocalFilesystemWorkspaceAdapter
from adapters.tests.support import FIXTURES


class LocalFilesystemAdapterTests(unittest.TestCase):
    def test_existing_workspace_uses_current_os_access(self) -> None:
        adapter = LocalFilesystemWorkspaceAdapter()
        root = FIXTURES / "filesystem_workspace"
        result = adapter.probe(root)
        self.assertEqual(result.outcome, AccessOutcome.REACHABLE)
        self.assertTrue(result.readable)
        self.assertTrue(result.existing_os_access)
        self.assertFalse(result.mutated)
        self.assertEqual(result.address.canonical_uri, root.resolve().as_uri())

    def test_missing_workspace_is_not_created(self) -> None:
        adapter = LocalFilesystemWorkspaceAdapter()
        missing = FIXTURES / "filesystem_workspace" / "never-created"
        self.assertFalse(missing.exists())
        result = adapter.probe(missing)
        self.assertEqual(result.outcome, AccessOutcome.UNREACHABLE)
        self.assertFalse(result.readable)
        self.assertFalse(result.mutated)
        self.assertFalse(missing.exists())

    def test_local_file_uri_round_trips(self) -> None:
        adapter = LocalFilesystemWorkspaceAdapter()
        root = FIXTURES / "filesystem_workspace"
        parsed = adapter.parse(root.resolve().as_uri())
        self.assertEqual(parsed.path, root.resolve())


if __name__ == "__main__":
    unittest.main()
