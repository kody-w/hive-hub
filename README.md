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

## Universal Agent Skill

`skills/hive-hub/` is a complete Agent Skill for a person or any AI. Copy that
folder into a tool's skills directory and ask it to:

- “dial this hive”
- “join this hive on this device and tell me when you are ready”
- scan a camera/QR Hive card

It accepts a public or private GitHub URL, `owner/repo at branch`, a local path,
a seven-word chant, a full Dial Record ID, or QR/AI join-card JSON. An optional
workspace address can accompany any request.

The locked Python 3.11+ runner uses only the standard library and must run with
isolated mode:

```bash
cd skills/hive-hub
python3 -I -B scripts/run.py decode --locator 'owner/repo at branch'
python3 -I -B scripts/run.py join --locator 'owner/repo at branch'
python3 -I -B scripts/run.py join --locator 'owner/repo at branch' \
  --apply '<exact returned plan digest>'
```

Every network read, local write, or verified adapter execution is planned
first. Existing source access is used without prompting or credential output.
Unknown protocols remain inert and return one blocker with their
content-addressed learning bundle.

## Verify

All validation is local and dependency-free:

```bash
python3 -B -m unittest discover -s tests -v
python3 scripts/check.py
python3 scripts/prove.py
```

`prove.py` also copies the skill to a path with spaces and verifies that the
copied folder operates without repository context.
