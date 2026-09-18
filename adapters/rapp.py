"""Read-only bridge to installed RAPP Work or RAPP Hive authority tooling."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .contracts import (
    AccessOutcome,
    AdapterDeclaration,
    CapabilityRequirement,
    ConformanceContract,
    PrivateAccessMode,
    ProtocolFingerprint,
    RequirementLevel,
    canonical_json,
    contract_document,
    require,
)

RAPP_DELEGATE_PROTOCOL = "hive-hub-rapp-delegate/1.0"
RAPP_DELEGATE_REQUEST_SCHEMA = "hive-hub-rapp-delegate-request/1.0"
RAPP_DELEGATE_RESULT_SCHEMA = "hive-hub-rapp-delegate-result/1.0"
MAX_DELEGATE_OUTPUT = 1_048_576
READ_ONLY_OPERATIONS = frozenset(
    {"describe", "inspect", "learn", "probe", "read", "verify"}
)
SECRET_FIELD_PARTS = frozenset(
    {"credential", "password", "private-key", "private_key", "secret", "token"}
)

_RAPP_DELEGATE_CONTRACT = {
    "schema": RAPP_DELEGATE_PROTOCOL,
    "accepted_tools": ["rapp-work", "rapp-hive"],
    "interface": "hive-hub-adapter --read-only --stdio-json",
    "operations": sorted(READ_ONLY_OPERATIONS),
    "authority": "delegate-only",
    "generic_rapp_fallback": False,
    "unknown_protocol_fallback": False,
    "secrets_in_payload": False,
    "writes": False,
}
RAPP_DELEGATE_FINGERPRINT, RAPP_DELEGATE_LEARNING = contract_document(
    RAPP_DELEGATE_PROTOCOL,
    _RAPP_DELEGATE_CONTRACT,
    source="embedded:hive-hub/rapp-delegate/1.0",
)
RAPP_DELEGATE_DECLARATION = AdapterDeclaration(
    adapter_id="rapp-authority-delegate",
    fingerprint=RAPP_DELEGATE_FINGERPRINT,
    capabilities=(
        CapabilityRequirement(
            "installed-rapp-tool",
            RequirementLevel.REQUIRED,
            "Authority operations are performed only by an accepted installed delegate.",
        ),
        CapabilityRequirement(
            "authority-reimplementation",
            RequirementLevel.FORBIDDEN,
            "The bridge validates only its envelope and never replays RAPP authority.",
        ),
        CapabilityRequirement(
            "generic-rapp-fallback",
            RequirementLevel.FORBIDDEN,
            "The unrelated legacy rapp command is never selected as authority tooling.",
        ),
        CapabilityRequirement(
            "remote-write",
            RequirementLevel.FORBIDDEN,
            "Only the bounded read-only delegate operation set is exposed.",
        ),
    ),
    private_access_modes=(PrivateAccessMode.DELEGATED,),
    learning_bundle=RAPP_DELEGATE_LEARNING,
    conformance=ConformanceContract(
        profile="hive-hub-rapp-delegate-conformance/1.0",
        fixtures=("adapters/fixtures/rapp_delegate_vectors.json",),
        assertions=(
            "accepted-tool-only",
            "authority-delegated",
            "unknown-protocol-no-fallback",
            "mutation-operations-refused",
            "secret-payload-refused",
            "stderr-never-returned",
        ),
    ),
    authority_model=(
        "Installed RAPP Work/RAPP Hive tooling remains the sole authority "
        "implementation."
    ),
)


class RappToolKind(str, Enum):
    WORK = "rapp-work"
    HIVE = "rapp-hive"


@dataclass(frozen=True)
class RappDelegateCommand:
    kind: RappToolKind
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        require(
            bool(self.command) and all(bool(part) for part in self.command),
            "invalid-rapp-delegate",
            "A RAPP delegate command must be non-empty.",
        )
        require(
            os.path.basename(self.command[0]) == self.kind.value,
            "unaccepted-rapp-delegate",
            "Only accepted RAPP Work or RAPP Hive executables may delegate authority.",
        )


RappRunner = Callable[
    [Sequence[str], bytes, Mapping[str, str], float],
    tuple[int, bytes],
]


def _run_delegate(
    command: Sequence[str],
    request: bytes,
    environment: Mapping[str, str],
    timeout: float,
) -> tuple[int, bytes]:
    try:
        completed = subprocess.run(
            tuple(command),
            input=request,
            check=False,
            env=dict(environment),
            stdin=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 255, b""
    output = completed.stdout
    if len(output) > MAX_DELEGATE_OUTPUT:
        return 255, b""
    return completed.returncode, output


def _contains_secret_field(value: object) -> bool:
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized = str(key).lower().replace(" ", "-")
                if any(part in normalized for part in SECRET_FIELD_PARTS):
                    return True
                stack.append(child)
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    return False


@dataclass(frozen=True)
class RappDelegateResult:
    schema: str
    tool: RappToolKind
    protocol_fingerprint: str
    operation: str
    outcome: AccessOutcome
    result: object | None
    delegated: bool
    authority_reimplemented: bool = False


class RappDelegatingAdapter:
    declaration = RAPP_DELEGATE_DECLARATION

    def __init__(
        self,
        delegates: tuple[RappDelegateCommand, ...] = (),
        runner: RappRunner = _run_delegate,
    ) -> None:
        self._delegates = {delegate.kind: delegate for delegate in delegates}
        self._runner = runner

    @classmethod
    def discover(
        cls,
        *,
        which: Callable[[str], str | None] = shutil.which,
        runner: RappRunner = _run_delegate,
    ) -> RappDelegatingAdapter:
        delegates = []
        for kind in (RappToolKind.WORK, RappToolKind.HIVE):
            executable = which(kind.value)
            if executable is not None:
                delegates.append(
                    RappDelegateCommand(
                        kind=kind,
                        command=(
                            executable,
                            "hive-hub-adapter",
                            "--read-only",
                            "--stdio-json",
                        ),
                    )
                )
        return cls(tuple(delegates), runner=runner)

    def available(self) -> tuple[RappToolKind, ...]:
        return tuple(sorted(self._delegates, key=lambda item: item.value))

    def invoke(
        self,
        *,
        tool: RappToolKind,
        operation: str,
        protocol_fingerprint: str,
        payload: Mapping[str, object],
        timeout: float = 30.0,
        environment: Mapping[str, str] | None = None,
    ) -> RappDelegateResult:
        require(
            operation in READ_ONLY_OPERATIONS,
            "rapp-mutation-refused",
            "The RAPP adapter exposes only read-only delegated operations.",
        )
        ProtocolFingerprint.parse(protocol_fingerprint)
        require(
            not _contains_secret_field(payload),
            "secret-payload-refused",
            "Credentials and secrets must remain ambient and cannot enter delegation payloads.",
        )
        delegate = self._delegates.get(tool)
        if delegate is None:
            return RappDelegateResult(
                schema=RAPP_DELEGATE_RESULT_SCHEMA,
                tool=tool,
                protocol_fingerprint=protocol_fingerprint,
                operation=operation,
                outcome=AccessOutcome.INERT,
                result=None,
                delegated=False,
            )
        require(
            0.0 < timeout <= 120.0,
            "invalid-delegate-timeout",
            "RAPP delegate timeout is outside the bounded profile.",
        )
        request = {
            "schema": RAPP_DELEGATE_REQUEST_SCHEMA,
            "tool": tool.value,
            "operation": operation,
            "protocol_fingerprint": protocol_fingerprint,
            "payload": dict(payload),
            "read_only": True,
        }
        env = dict(os.environ if environment is None else environment)
        env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
                "GH_PROMPT_DISABLED": "1",
            }
        )
        return_code, output = self._runner(
            delegate.command,
            canonical_json(request),
            env,
            timeout,
        )
        if return_code != 0:
            return RappDelegateResult(
                schema=RAPP_DELEGATE_RESULT_SCHEMA,
                tool=tool,
                protocol_fingerprint=protocol_fingerprint,
                operation=operation,
                outcome=AccessOutcome.UNREACHABLE,
                result=None,
                delegated=True,
            )
        try:
            decoded: Any = json.loads(output)
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = None
        require(
            type(decoded) is dict
            and set(decoded)
            == {
                "schema",
                "tool",
                "protocol_fingerprint",
                "operation",
                "outcome",
                "result",
            }
            and decoded["schema"] == RAPP_DELEGATE_RESULT_SCHEMA
            and decoded["tool"] == tool.value
            and decoded["protocol_fingerprint"] == protocol_fingerprint
            and decoded["operation"] == operation
            and decoded["outcome"]
            in {
                AccessOutcome.REACHABLE.value,
                AccessOutcome.UNREACHABLE.value,
                AccessOutcome.INERT.value,
            },
            "invalid-rapp-delegate-result",
            "The installed RAPP tool returned an invalid delegation envelope.",
        )
        require(
            not _contains_secret_field(decoded["result"]),
            "secret-result-refused",
            "The installed RAPP tool returned secret-bearing data.",
        )
        return RappDelegateResult(
            schema=RAPP_DELEGATE_RESULT_SCHEMA,
            tool=tool,
            protocol_fingerprint=protocol_fingerprint,
            operation=operation,
            outcome=AccessOutcome(decoded["outcome"]),
            result=decoded["result"],
            delegated=True,
        )
