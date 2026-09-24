---
card: protocol
id: hive-md
name: Hive folder convention (HIVE-MD)
status: experimental
spec: https://github.com/kody-w/rapp-model-hive/blob/2bd7c95152ede719b6418b80e2bdc2cd457bf711/HIVE-MD.md
spec_sha256: f3186e0d88cc36e18582171fff4ed9a68feddc4ae316f66fb8acc2982892fd96
checker: python agents/hive_agent.py check <hive>
checker_sha256: e9a2d7243da31fd2388f140bb8138c3d8d2db428ad09075530eb049a0355e8dd
agent: https://github.com/kody-w/rapp-model-hive/blob/2bd7c95152ede719b6418b80e2bdc2cd457bf711/agents/hive_agent.py
agent_sha256: e9a2d7243da31fd2388f140bb8138c3d8d2db428ad09075530eb049a0355e8dd
---

A Hive is a git repository of markdown files: `HIVE.md`, `members/<name>/keys/<device>.md`,
`requests/`, `shared/` and `former/`. Every change is an SSH-signed commit, judged by the Hive
as it stood at its parent. The checker and the agent are one file from the same commit as the
spec. The agent's `join` takes the address and the root commit (as `id`), checks every commit
from that root, pins the root and the Hive id, and shows the founder key fingerprint, which must
match the Hive card. Experimental: it is in the frontier track's canary ring and has not yet
been used by a real team for a real week.
