# Defensive boundary

**SYNTHETIC fixtures. Ordinary logic defects, not a claim of exploitable
vulnerabilities.** This source package has not undergone a security audit.

The program reads one explicitly selected bounded ordinary file, parses
strict JSON records, validates a small allowlisted shape, and writes a JSON
summary to stdout. No fixture is imported as Python or interpreted as a
shell command. There are no executable payloads, callback URLs, remote
dependencies, secrets, system modifications, or identity material.

The reference refuses files above 1 MiB, lines above 16 KiB, more than 5,000
events, unknown fields, conflicting event IDs, and invalid minute values.
Tests create only harmless dictionaries and strings in memory. They do not
probe the host, access private files, create network listeners, or attempt
adversarial actions against a real service.

Review proposed fixes for accidental capability growth: a reducer does not
need filesystem writes, dynamic imports, subprocesses, networking, runtime
plugins, or repository discovery. Keep input path selection explicit. The CLI
rejects symlinks and non-regular inputs for this reference boundary.

If a later contributor reports a genuine vulnerability, follow the real
owner's approved reporting process and use a minimal inert reproduction.
Do not post credentials or private logs, and do not fabricate a disclosure
endpoint or assurance claim for this seed.
