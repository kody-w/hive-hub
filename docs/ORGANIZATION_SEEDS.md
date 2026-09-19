# Public RAPP Work organization seeds

These are complete starter packages, not prompts or activated companies.
Browse [the catalog](https://kody-w.github.io/hive-hub/hub/#organizations) or
read [its static API](https://kody-w.github.io/hive-hub/api/hive-hub/v1/organization-seeds.json).

Give any AI the complete
[global network skill](https://kody-w.github.io/hive-hub/hub/skills/hive-network/SKILL.md).
It covers discovery, local setup through the trusted native SDK, scoped work,
and owner-reviewed public contributions. A web-only AI can inspect; it cannot
claim to create local files or submit changes without those capabilities.

| Organization | Seed |
| --- | --- |
| The One-Person Conglomerate | [Open](https://kody-w.github.io/hive-hub/hub/seeds/one-person-conglomerate/) |
| The Enterprise Transformation Firm | [Open](https://kody-w.github.io/hive-hub/hub/seeds/enterprise-transformation-firm/) |
| The Product Launch Company | [Open](https://kody-w.github.io/hive-hub/hub/seeds/product-launch-company/) |
| The Open-Source Infrastructure Foundation | [Open](https://kody-w.github.io/hive-hub/hub/seeds/open-source-infrastructure-foundation/) |
| The Applied Invention Lab | [Open](https://kody-w.github.io/hive-hub/hub/seeds/applied-invention-lab/) |
| The Independent Game Studio | [Open](https://kody-w.github.io/hive-hub/hub/seeds/independent-game-studio/) |
| The Micro-Manufacturing Company | [Open](https://kody-w.github.io/hive-hub/hub/seeds/micro-manufacturing-company/) |
| The Public-Source Intelligence Bureau | [Open](https://kody-w.github.io/hive-hub/hub/seeds/public-source-intelligence-bureau/) |
| The Turnaround Firm | [Open](https://kody-w.github.io/hive-hub/hub/seeds/turnaround-firm/) |
| The Federation Prime Contractor | [Open](https://kody-w.github.io/hive-hub/hub/seeds/federation-prime-contractor/) |

## Package contents

- `seed.json`: package classification, exact dependency pins, and file inventory.
- `initialize.json`: native Organization/Workspace scaffold inputs, team ownership,
  template mappings, and same-world pointer registration requirements.
- `templates/teams/<team>/work/`: scoped team purpose, owned work, and acceptance.
- `templates/casework/work/`: synthetic intake, dependency-linked task board,
  success criteria, and original usable starter artifacts.
- `README.md`: initialization and operating instructions.

All starter task ownership and prerequisites are explicit. A task with no
prerequisites is ready to claim; dependent tasks are blocked. No task is
silently assigned or marked completed. Reference programs, designs, and reports
are examples, not proof that a customer's engagement has been delivered.

## Initialize, do not impersonate

Give the verified seed to a capable AI host with the exact locally trusted
RAPP Work SDK. Choose your owner label and a new destination. The seed does not
contain an organization RAPPID or another person's private state.

Use the canonical SDK to plan the Organization and each member Workspace.
Approve each complete native plan and its exact digest before applying it.
Review the declared template-copy effects and native `Organization.plan_register`
plans separately. Register only same-world workspace pointers. Do not copy team
contents into the Organization or register external partners across worlds.

Joining through Hive Hub saves only a reversible local subscription and returns
an inert next step. It does not initialize the organization, install an SDK, run
downloaded code, grant access, or activate a federation. An unavailable SDK,
missing owner authorization, or an incapable host is a blocker, not success.

The prime contractor's partner references are candidate briefs. Actual external
communication, publication, spending, membership, or signing still requires
the appropriate owner authorization.

## Rebuild and verify

```bash
npm run sync:release
npm run verify
PYTHONPATH=src:. python3 -B -m unittest tests.test_organization_seeds
python3 -B scripts/check_organization_seeds.py --exercise-native \
  --sdk-path /exact/qualified/rapp-work \
  --rapp1-path /exact/qualified/rapp-1
```

The native conformance command requires the exact clean dependencies pinned by
`seed-src/SDK_PIN.json`. It initializes and verifies all organizations and member
workspaces in isolated temporary fixtures and removes those fixtures afterward.
That is structural and initialization evidence, not a signed business-protocol
receipt or activation of a user's organization.

Seed sources are bounded and individually allowlisted under `seed-src/`.
Builds never discover, read, copy, or republish private Hive state.
