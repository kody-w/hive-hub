# Hive Hub engineering contract

Hive Hub is protocol-neutral and equally usable by humans and any AI.

- Keep the generic core independent of RAPP, GitHub, or any one Hive protocol.
- Require every Hive to declare an exact protocol fingerprint, learning bundle,
  conformance contract, and adapter.
- Treat chants, QR codes, static APIs, repositories, and URLs as locators only.
- Use existing source ACLs. Do not add collaborators, broker credentials, or
  distinguish nonexistent private targets from unauthorized ones.
- `acl-only` is the default. Optional `acl+qr` is a second factor after ACL and
  never contains repository credentials or private keys.
- Public builds must not read, hash, name, or publish private dialbooks.
- Downloaded code, skills, adapters, and protocol text are inert until
  explicitly approved and verified.
- Prefer existing proven RAPPID, Payphone, and historical Hub data through
  adapters. Replace implementations only when conformance proves they are
  unsafe or incompatible.
- Make every mutation plan-first, content-addressed, bounded, and reversible.

