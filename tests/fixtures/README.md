# Local-only Hive Hub fixtures

The test suite builds every repository, declaration, dialbook, QR payload, and
device root under `tests/.work/`. No test contacts GitHub or any other network
service. GitHub-shaped tests redirect the runner to a local bare Git repository
through the runner's explicitly gated `HIVE_HUB_LOCAL_TESTING=1` fixture seam.

Static card samples in this folder contain locators only. Tests that exercise an
unlock fragment construct it in memory, pass it through standard input, and
assert that it never appears in output or persisted files.
