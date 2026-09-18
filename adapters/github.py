"""Read-only GitHub repository locator and ambient-credential access probe."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

from .contracts import (
    AccessOutcome,
    AdapterDeclaration,
    CapabilityRequirement,
    ConformanceContract,
    PrivateAccessMode,
    RequirementLevel,
    contract_document,
    require,
)

_OWNER_RE = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?\Z",
    re.ASCII,
)
_REPOSITORY_RE = re.compile(r"[a-z0-9._-]{1,100}\Z", re.ASCII)
_CONTROL_RE = re.compile(r"[\x00-\x20\x7f]", re.ASCII)

GITHUB_PROTOCOL = "hive-hub-github-repository/1.0"
_GITHUB_CONTRACT = {
    "schema": GITHUB_PROTOCOL,
    "address_forms": [
        "owner/repo",
        "owner/repo at branch",
        "owner/repo/tree/branch",
        "https://github.com/owner/repo/tree/branch",
        "git@github.com:owner/repo.git",
    ],
    "canonical_url": "https://github.com/<owner>/<repo>",
    "probe": {
        "command": "git ls-remote --exit-code",
        "credentials": "ambient-caller-only",
        "prompts": False,
        "writes": False,
        "nonzero": "unreachable",
    },
}
GITHUB_FINGERPRINT, GITHUB_LEARNING = contract_document(
    GITHUB_PROTOCOL,
    _GITHUB_CONTRACT,
    source="embedded:hive-hub/github-repository/1.0",
)
GITHUB_DECLARATION = AdapterDeclaration(
    adapter_id="github-repository",
    fingerprint=GITHUB_FINGERPRINT,
    capabilities=(
        CapabilityRequirement(
            "git-read",
            RequirementLevel.REQUIRED,
            "Repository reachability is checked with git ls-remote.",
        ),
        CapabilityRequirement(
            "caller-credentials",
            RequirementLevel.OPTIONAL,
            "Private repositories use only credentials already available to Git.",
        ),
        CapabilityRequirement(
            "interactive-prompts",
            RequirementLevel.FORBIDDEN,
            "The probe must never solicit credentials.",
        ),
        CapabilityRequirement(
            "acl-mutation",
            RequirementLevel.FORBIDDEN,
            "The adapter never adds collaborators or changes source ACLs.",
        ),
        CapabilityRequirement(
            "remote-write",
            RequirementLevel.FORBIDDEN,
            "The only remote command is git ls-remote.",
        ),
    ),
    private_access_modes=(
        PrivateAccessMode.PUBLIC,
        PrivateAccessMode.ACL_ONLY,
    ),
    learning_bundle=GITHUB_LEARNING,
    conformance=ConformanceContract(
        profile="hive-hub-github-conformance/1.0",
        fixtures=("adapters/fixtures/github_vectors.json",),
        assertions=(
            "canonical-address-parity",
            "ambient-credentials-only",
            "prompts-disabled",
            "absent-unauthorized-indistinguishable",
            "no-token-logging",
            "no-remote-writes",
        ),
    ),
    authority_model="GitHub source ACLs remain authoritative; this adapter only probes.",
)


def _validate_branch(branch: str) -> str:
    branch = unquote(branch)
    require(
        bool(branch)
        and len(branch.encode("utf-8")) <= 1024
        and _CONTROL_RE.search(branch) is None
        and not branch.startswith(("-", "/", "."))
        and not branch.endswith(("/", ".", ".lock"))
        and ".." not in branch
        and "@{" not in branch
        and "//" not in branch
        and not any(character in branch for character in "~^:?*[\\"),
        "invalid-github-branch",
        "The GitHub branch is not a valid bounded Git ref.",
    )
    return branch


def _validate_owner(owner: str) -> str:
    owner = owner.lower()
    require(
        _OWNER_RE.fullmatch(owner) is not None and "--" not in owner,
        "invalid-github-owner",
        "The GitHub owner is invalid.",
    )
    return owner


def _validate_repository(repository: str) -> str:
    repository = unquote(repository).lower().removesuffix(".git")
    require(
        _REPOSITORY_RE.fullmatch(repository) is not None
        and repository not in {".", ".."}
        and not repository.endswith("."),
        "invalid-github-repository",
        "The GitHub repository name is invalid.",
    )
    return repository


@dataclass(frozen=True)
class GitHubRepositoryAddress:
    owner: str
    repository: str
    branch: str | None = None

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repository}"

    @property
    def canonical_url(self) -> str:
        return f"https://github.com/{self.slug}"

    @property
    def tree_url(self) -> str | None:
        if self.branch is None:
            return None
        return f"{self.canonical_url}/tree/{quote(self.branch, safe='/')}"

    @property
    def display(self) -> str:
        if self.branch is None:
            return self.slug
        return f"{self.slug} at {self.branch}"


def parse_github_address(value: str) -> GitHubRepositoryAddress:
    require(
        type(value) is str and bool(value.strip()),
        "invalid-github-address",
        "A GitHub repository address must be a non-empty string.",
    )
    raw = value.strip()
    explicit_branch: str | None = None
    if " at " in raw:
        raw, explicit_branch = raw.rsplit(" at ", 1)
        explicit_branch = _validate_branch(explicit_branch.strip())
        raw = raw.strip()

    if raw.startswith("git@github.com:"):
        path = raw[len("git@github.com:") :]
    elif "://" in raw:
        parsed = urlsplit(raw)
        require(
            parsed.scheme == "https"
            and (parsed.hostname or "").lower() == "github.com"
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and not parsed.query
            and not parsed.fragment,
            "invalid-github-address",
            "Only canonical HTTPS GitHub repository URLs are accepted.",
        )
        path = parsed.path.lstrip("/")
    else:
        path = raw.lstrip("/")

    segments = path.rstrip("/").split("/")
    require(
        len(segments) >= 2 and all(segments[:2]),
        "invalid-github-address",
        "A GitHub address must name owner/repository.",
    )
    owner = _validate_owner(unquote(segments[0]))
    repository = _validate_repository(segments[1])
    path_branch: str | None = None
    if len(segments) > 2:
        require(
            len(segments) >= 4 and segments[2] == "tree",
            "invalid-github-address",
            "Only /tree/<branch> may follow owner/repository.",
        )
        path_branch = _validate_branch("/".join(segments[3:]))
    if explicit_branch is not None and path_branch is not None:
        require(
            explicit_branch == path_branch,
            "conflicting-github-branch",
            "The address declares two different branches.",
        )
    return GitHubRepositoryAddress(
        owner=owner,
        repository=repository,
        branch=explicit_branch or path_branch,
    )


GitRunner = Callable[[Sequence[str], Mapping[str, str], float], int]


def _run_git(
    command: Sequence[str],
    environment: Mapping[str, str],
    timeout: float,
) -> int:
    try:
        completed = subprocess.run(
            tuple(command),
            check=False,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 255
    return completed.returncode


@dataclass(frozen=True)
class GitHubAccessProbe:
    address: GitHubRepositoryAddress
    outcome: AccessOutcome
    credential_mode: str = "ambient-caller-only"
    prompts_enabled: bool = False
    remote_writes: bool = False


class GitHubRepositoryAdapter:
    declaration = GITHUB_DECLARATION

    def __init__(self, runner: GitRunner = _run_git) -> None:
        self._runner = runner

    def parse(self, value: str) -> GitHubRepositoryAddress:
        return parse_github_address(value)

    def probe(
        self,
        address: str | GitHubRepositoryAddress,
        *,
        timeout: float = 15.0,
        environment: Mapping[str, str] | None = None,
    ) -> GitHubAccessProbe:
        require(
            0.0 < timeout <= 120.0,
            "invalid-probe-timeout",
            "GitHub probe timeout is outside the bounded profile.",
        )
        parsed = parse_github_address(address) if isinstance(address, str) else address
        env = dict(os.environ if environment is None else environment)
        env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GCM_INTERACTIVE": "Never",
                "GH_PROMPT_DISABLED": "1",
                "SSH_ASKPASS_REQUIRE": "never",
            }
        )
        command = [
            "git",
            "-c",
            "credential.interactive=never",
            "ls-remote",
            "--exit-code",
            parsed.canonical_url,
        ]
        if parsed.branch is not None:
            command.append(f"refs/heads/{parsed.branch}")
        outcome = (
            AccessOutcome.REACHABLE
            if self._runner(command, env, timeout) == 0
            else AccessOutcome.UNREACHABLE
        )
        return GitHubAccessProbe(address=parsed, outcome=outcome)
