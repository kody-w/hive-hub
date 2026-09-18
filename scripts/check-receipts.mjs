import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import { lstat, readFile } from "node:fs/promises";
import path from "node:path";

import {
  isMain,
  parseCliArgs,
  readPublicFile,
  sha256Bytes
} from "./lib/canonical.mjs";
import { loadPublicInputs } from "./lib/public-inputs.mjs";

const execFile = promisify(execFileCallback);

async function git(repository, args) {
  return execFile("git", ["-C", repository, ...args], {
    encoding: null,
    maxBuffer: 10 * 1024 * 1024
  });
}

async function gitShowOrNull(repository, revisionPath) {
  try {
    const result = await git(repository, ["show", revisionPath]);
    return result.stdout;
  } catch (error) {
    if (error.code === 128 || error.stderr?.toString().includes("does not exist")) {
      return null;
    }
    throw error;
  }
}

function receiptEntries(manifest) {
  return manifest.entries.filter((entry) => entry.kind === "receipt");
}

export function allowsLedgerWithdrawal(policy, priorManifestBytes) {
  if (
    !policy ||
    Object.keys(policy).sort().join(",") !== "kind,manifestSha256,version" ||
    policy.kind !== "public-ledger-withdrawals" ||
    policy.version !== 1 ||
    !Array.isArray(policy.manifestSha256) ||
    policy.manifestSha256.length > 128 ||
    !policy.manifestSha256.every((digest) => /^[a-f0-9]{64}$/.test(digest)) ||
    new Set(policy.manifestSha256).size !== policy.manifestSha256.length
  ) {
    throw new Error("Invalid public ledger withdrawal policy");
  }
  return policy.manifestSha256.includes(sha256Bytes(priorManifestBytes));
}

async function requireWithdrawnPath(repository, relative) {
  const absolute = path.resolve(repository, relative);
  if (!absolute.startsWith(path.resolve(repository) + path.sep)) {
    throw new Error("Withdrawn path escapes the repository");
  }
  try {
    await lstat(absolute);
  } catch (error) {
    if (error.code === "ENOENT") {
      return;
    }
    throw error;
  }
  throw new Error(`Withdrawn receipt is still present: ${relative}`);
}

export async function checkReceipts({ manifestPath, base }) {
  const loaded = await loadPublicInputs(manifestPath);
  const repository = loaded.manifestDirectory;
  const currentEntries = receiptEntries(loaded.manifest);
  const sequences = loaded.entries
    .filter((entry) => entry.declaration.kind === "receipt")
    .map((entry) => entry.document.sequence)
    .sort((left, right) => left - right);
  sequences.forEach((sequence, index) => {
    if (sequence !== index + 1) {
      throw new Error(`Receipt source sequence is not contiguous at ${sequence}`);
    }
  });

  const receiptIndex = JSON.parse(
    await readPublicFile(repository, "api/hive-hub/v1/receipts/index.json")
  );
  if (receiptIndex.appendOnly !== true || receiptIndex.receipts.length !== currentEntries.length) {
    throw new Error("Generated receipt index does not match the append-only source ledger");
  }
  for (const descriptor of receiptIndex.receipts) {
    const bytes = await readPublicFile(repository, descriptor.path);
    if (`sha256:${sha256Bytes(bytes)}` !== descriptor.ref) {
      throw new Error(`Immutable receipt hash mismatch: ${descriptor.path}`);
    }
  }

  if (!base) {
    return {
      comparedBase: false,
      count: currentEntries.length
    };
  }

  const priorManifestBytes = await gitShowOrNull(repository, `${base}:public-manifest.json`);
  if (!priorManifestBytes) {
    return {
      comparedBase: true,
      count: currentEntries.length,
      priorLedger: false
    };
  }
  const priorManifest = JSON.parse(priorManifestBytes);
  const priorEntries = receiptEntries(priorManifest);
  const priorTree = await git(repository, [
    "ls-tree", "-r", "--name-only", base, "--", "api/hive-hub/v1/receipts/sha256"
  ]);
  const priorReceiptPaths = priorTree.stdout.toString("utf8").trim().split("\n").filter(Boolean);
  let withdrawalPolicy = null;
  try {
    withdrawalPolicy = JSON.parse(await readPublicFile(repository, "public-withdrawals.json"));
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }
  if (withdrawalPolicy && allowsLedgerWithdrawal(withdrawalPolicy, priorManifestBytes)) {
    for (const prior of priorEntries) {
      if (currentEntries.some((entry) => entry.id === prior.id || entry.path === prior.path)) {
        throw new Error("Withdrawn receipt declarations must not be reused");
      }
      await requireWithdrawnPath(repository, `${priorManifest.sourceRoot}/${prior.path}`);
      await requireWithdrawnPath(repository, `api/hive-hub/v1/source/${prior.path}`);
    }
    for (const receiptPath of priorReceiptPaths) {
      await requireWithdrawnPath(repository, receiptPath);
    }
    return {
      comparedBase: true,
      count: currentEntries.length,
      priorLedger: true,
      priorReceiptCount: priorEntries.length,
      withdrawnLedger: true
    };
  }
  if (currentEntries.length < priorEntries.length) {
    throw new Error("Append-only receipt ledger removed prior receipt declarations");
  }
  for (let index = 0; index < priorEntries.length; index += 1) {
    const prior = priorEntries[index];
    const current = currentEntries[index];
    if (
      prior.id !== current.id ||
      prior.path !== current.path ||
      prior.sha256 !== current.sha256
    ) {
      throw new Error(`Receipt declaration ${prior.id} was changed or reordered`);
    }
    const priorSource = await gitShowOrNull(
      repository,
      `${base}:${priorManifest.sourceRoot}/${prior.path}`
    );
    if (!priorSource) {
      throw new Error(`Prior receipt source is missing at ${prior.path}`);
    }
    const currentSource = await readFile(
      path.join(repository, loaded.manifest.sourceRoot, current.path)
    );
    if (!priorSource.equals(currentSource)) {
      throw new Error(`Prior receipt source was modified: ${prior.path}`);
    }
  }

  for (const receiptPath of priorReceiptPaths) {
    const priorBytes = await gitShowOrNull(repository, `${base}:${receiptPath}`);
    const currentBytes = await readPublicFile(repository, receiptPath);
    if (!priorBytes.equals(currentBytes)) {
      throw new Error(`Published immutable receipt changed: ${receiptPath}`);
    }
  }

  return {
    comparedBase: true,
    count: currentEntries.length,
    priorLedger: true,
    priorReceiptCount: priorEntries.length
  };
}

async function main() {
  const args = parseCliArgs(process.argv.slice(2));
  if (!args.manifest) {
    throw new Error(
      "Usage: node scripts/check-receipts.mjs --manifest public-manifest.json [--base <git-ref>]"
    );
  }
  const result = await checkReceipts({
    base: args.base,
    manifestPath: args.manifest
  });
  const baseMessage = result.comparedBase
    ? result.withdrawnLedger
      ? `; verified removal of ${result.priorReceiptCount} explicitly withdrawn receipt(s)`
      : result.priorLedger
      ? ` and preserved ${result.priorReceiptCount} receipt(s) from the base`
      : "; the base has no prior ledger"
    : "";
  process.stdout.write(`Validated ${result.count} append-only receipt(s)${baseMessage}.\n`);
}

if (isMain(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 1;
  });
}
