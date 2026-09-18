# Hive Hub

Hive Hub lets people and any AI discover, learn, dial, and join public or
private Hives without requiring one ecosystem or protocol.

The Hub core is protocol-neutral. Every Hive declares its actual protocol and
publishes a content-addressed learning bundle or adapter contract. Our Hives
use the accepted RAPP Work, RAPP Hive, RAPPID chant, and Payphone adapters, but
non-RAPP Hives participate through their own declared adapters.

Chants, QR codes, URLs, Git references, and static APIs are locators and
learning transports, never authority. Existing source access remains required.
Private nonexistent and unauthorized targets return the same unreachable
result. A private Hive may optionally require an additional QR-only factor
after its normal ACL succeeds.

The public Hub contains only public records. Private records and optional QR
unlock commitments remain local or inside the already-authorized private Hive.

## Neutral adapter package

`adapters/` is a stdlib-only, typed source tree that can be merged into the
core package without importing any RAPP runtime:

| Adapter | Exact protocol |
|---|---|
| GitHub repository locator/probe | `hive-hub-github-repository/1.0` |
| Local filesystem workspace | `hive-hub-local-workspace/1.0` |
| Installed RAPP Work/Hive delegate | `hive-hub-rapp-delegate/1.0` |
| Seven-word RAPPID chant | `rappidex/1-summon-chant` |
| Payphone DoorRef/dial result | `rapp-payphone-dial/1.0` |
| Historical Hub inspector | `legacy-rapp-hub/00ac2f73` |

Each declaration binds its protocol to canonical contract bytes with SHA-256
and includes capability requirements, supported private-access modes, an inert
learning bundle, and local conformance fixtures. The registry performs exact
fingerprint lookup only. An unknown fingerprint returns an inert adapter and
is never routed to RAPP.

The GitHub probe uses `git ls-remote` with caller-owned ambient credentials,
stdin closed, and interactive prompts disabled. Every nonzero response is the
same `unreachable` result, so an absent repository cannot be distinguished
from one the caller cannot access. It never changes repository ACLs or remote
state.

The chant adapter carries the frozen 128-word vocabulary and hash
`325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36`.
Chants remain 49-bit locators; collision buckets retain all complete RAPPIDs.
Payphone routing prefixes likewise never authorize: connection requires the
exact full RAPPID.

## Conformance

```sh
python3 -m unittest discover -s adapters/tests -v
ruff check adapters
mypy --strict adapters
```

Fixtures cover canonical GitHub forms, absent/unauthorized indistinguishability,
ambient-token hygiene, no remote writes, exact chant vectors and collision
buckets, new Payphone DoorRef vectors and truncated-ID collisions, and inert
historical malicious instructions.

## Explicit compatibility refusals

- The installed legacy `rapp` Rapid AI Agent Production Pipeline CLI is not a
  RAPP Work/Hive authority delegate. Only `rapp-work` and `rapp-hive` adapter
  entry points are considered.
- The historical RAPPidex “first repository wins” behavior is incompatible
  with collision-safe lookup and is not used.
- Legacy/provisional RAPPID forms are inspection or migration evidence, not
  active chant or Payphone inputs. Active parsing requires the exact lowercase
  RAPP/1 form with a 64-hex tail.
- Historical Payphone Issues/PR mutation rungs and the `no-answer` outcome are
  outside this neutral read-only adapter. Its result is only `connected` or
  `unreachable`.
- `RAPP_Hub@00ac2f73` server, Docker, skill, and instruction surfaces are never
  downloaded, installed, imported, or executed. The adapter reads bounded
  already-local JSON only.
