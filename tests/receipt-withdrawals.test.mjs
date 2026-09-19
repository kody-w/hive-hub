import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { buildStaticSurface } from "../scripts/build.mjs";
import { allowsLedgerWithdrawal, checkReceipts } from "../scripts/check-receipts.mjs";
import { canonicalJson, sha256Bytes } from "../scripts/lib/canonical.mjs";

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("withdrawal approval binds the exact prior manifest and rejects malformed policy", () => {
  const bytes = Buffer.from('{"fixture":"approved-public-ledger"}\n');
  const policy = {
    kind: "public-ledger-withdrawals",
    version: 1,
    manifestSha256: [sha256Bytes(bytes)]
  };
  assert.equal(allowsLedgerWithdrawal(policy, bytes), true);
  assert.equal(allowsLedgerWithdrawal(policy, Buffer.from("{}\n")), false);
  assert.throws(() => allowsLedgerWithdrawal({ ...policy, bypass: true }, bytes));
  assert.throws(() => allowsLedgerWithdrawal({ ...policy, manifestSha256: ["*"] }, bytes));
});

test("withdrawal requires explicit approval and removal of prior receipt bytes", async () => {
  const root = path.join(repository, "tests/.work/receipt-withdrawals");
  await mkdir(root, { recursive: true });
  const git = (...args) => {
    const result = spawnSync("git", ["-C", root, ...args], {
      encoding: "utf8",
      env: {
        ...process.env,
        GIT_AUTHOR_NAME: "Test",
        GIT_AUTHOR_EMAIL: "test@example.invalid",
        GIT_COMMITTER_NAME: "Test",
        GIT_COMMITTER_EMAIL: "test@example.invalid"
      }
    });
    assert.equal(result.status, 0, result.stderr);
    return result.stdout.trim();
  };
  try {
    await cp(path.join(repository, "public-src"), path.join(root, "public-src"), { recursive: true });
    const manifestBytes = await readFile(path.join(repository, "public-manifest.json"));
    const manifestPath = path.join(root, "public-manifest.json");
    await writeFile(manifestPath, manifestBytes);
    await buildStaticSurface({ manifestPath, outDir: root });
    git("init", "--quiet");
    git("add", ".");
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Fixture public ledger");
    const base = git("rev-parse", "HEAD");
    const oldIndex = JSON.parse(await readFile(path.join(root, "api/hive-hub/v1/receipts/index.json")));
    const oldReceiptPath = oldIndex.receipts[0].path;
    const oldReceipt = await readFile(path.join(root, oldReceiptPath));
    const manifest = JSON.parse(manifestBytes);
    const priorEntries = manifest.entries.filter((item) => item.kind === "receipt");
    const entry = { ...priorEntries[0] };
    const source = JSON.parse(await readFile(path.join(root, "public-src", entry.path)));
    source.ledger = "replacement-fixture";
    source.sequence = 1;
    entry.id = "fixture-replacement-receipt";
    entry.path = "receipts/0001-fixture-replacement.json";
    const sourceBytes = Buffer.from(canonicalJson(source));
    entry.sha256 = sha256Bytes(sourceBytes);
    await writeFile(path.join(root, "public-src", entry.path), sourceBytes);
    for (const prior of priorEntries) {
      await rm(path.join(root, "public-src", prior.path));
    }
    manifest.entries = manifest.entries.filter(
      (item) => item.kind !== "receipt" && item.kind !== "historical-receipt"
    );
    manifest.entries.push(entry);
    manifest.entries.sort((left, right) => left.id.localeCompare(right.id));
    await writeFile(manifestPath, canonicalJson(manifest));
    await buildStaticSurface({ manifestPath, outDir: root });
    await assert.rejects(checkReceipts({ manifestPath, base }), /removed prior|changed or reordered/);
    await writeFile(path.join(root, "public-withdrawals.json"), canonicalJson({
      kind: "public-ledger-withdrawals",
      version: 1,
      manifestSha256: [sha256Bytes(manifestBytes)]
    }));
    const checked = await checkReceipts({ manifestPath, base });
    assert.equal(checked.withdrawnLedger, true);
    await mkdir(path.dirname(path.join(root, oldReceiptPath)), { recursive: true });
    await writeFile(path.join(root, oldReceiptPath), oldReceipt);
    await assert.rejects(checkReceipts({ manifestPath, base }), /still present/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
