from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest import mock

from hive_hub.adapter_runtime import (
    adapters_available,
    builtin_adapter_contracts,
)
from hive_hub.canonical import content_address

from .helpers import PROJECT_ROOT, WorkspaceTestCase


class AdapterRuntimeTests(WorkspaceTestCase):
    def test_builtin_adapters_map_to_closed_core_contracts(self) -> None:
        self.assertTrue(adapters_available())
        contracts = builtin_adapter_contracts()
        self.assertEqual(len(contracts), 6)
        self.assertEqual(
            tuple(item.adapter_id for item in contracts),
            tuple(sorted(item.adapter_id for item in contracts)),
        )
        for item in contracts:
            self.assertTrue(item.source_fingerprint.endswith(item.source_fingerprint[-64:]))
            self.assertEqual(
                item.learning_bundle.protocol_fingerprint,
                item.declaration.fingerprint,
            )
            self.assertEqual(
                item.registration.protocol_fingerprint,
                item.declaration.fingerprint,
            )
            self.assertEqual(
                item.registration.conformance_address,
                item.declaration.conformance_address,
            )

    def test_core_remains_usable_when_adapter_package_is_absent(self) -> None:
        from hive_hub import adapter_runtime

        with mock.patch.object(
            adapter_runtime,
            "_adapter_modules",
            return_value=(None, None),
        ):
            self.assertFalse(adapter_runtime.adapters_available())
            self.assertEqual(adapter_runtime.builtin_adapter_contracts(), ())

    def test_cli_plans_then_installs_builtin_contracts(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(("src", ".", env.get("PYTHONPATH", "")))
        list_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "hive_hub",
                "--home",
                str(self.work),
                "adapter",
                "builtin",
                "list",
            ],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(list_result.returncode, 0, list_result.stderr)
        listing = json.loads(list_result.stdout)
        selected = listing["adapters"][0]
        planned = subprocess.run(
            [
                sys.executable,
                "-m",
                "hive_hub",
                "--home",
                str(self.work),
                "adapter",
                "builtin",
                "install",
                selected["adapter_id"],
            ],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(planned.returncode, 0, planned.stderr)
        plan = json.loads(planned.stdout)
        self.assertEqual(
            plan["plan_id"],
            content_address({key: value for key, value in plan.items() if key != "plan_id"}),
        )
        applied = subprocess.run(
            [
                sys.executable,
                "-m",
                "hive_hub",
                "--home",
                str(self.work),
                "adapter",
                "builtin",
                "install",
                selected["adapter_id"],
                "--apply",
                plan["plan_id"],
                "--registered-at",
                "2026-09-18T19:37:51Z",
            ],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        result = json.loads(applied.stdout)
        self.assertEqual(result["status"], "installed")
        self.assertFalse(result["adapter_execution"])
