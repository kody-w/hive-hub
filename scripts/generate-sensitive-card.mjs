import { spawnSync } from "node:child_process";
import { lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { canonicalJson, isMain, parseCliArgs } from "./lib/canonical.mjs";
import { createQrSvg } from "./lib/qr.mjs";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertLocalOutput(root, outDir) {
  const relative = path.relative(path.resolve(root), path.resolve(outDir)).split(path.sep).join("/");
  assert(
    relative === ".hive-hub/private-cards" ||
      relative.startsWith(".hive-hub/private-cards/") ||
      relative === "tests/.work" ||
      relative.startsWith("tests/.work/"),
    "Sensitive cards may be written only below .hive-hub/private-cards or tests/.work"
  );
  assert(!relative.startsWith("../") && relative !== "..", "Sensitive card output escapes the project");
}

function validateLocatorWithSkill(locator, projectRoot) {
  const runner = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../skills/hive-hub/scripts/run.py"
  );
  const result = spawnSync(
    process.env.PYTHON || "python3",
    ["-I", "-B", runner, "decode", "--locator", locator],
    {
      cwd: projectRoot,
      encoding: "utf8",
      env: process.env,
      maxBuffer: 1024 * 1024
    }
  );
  assert(
    result.status === 0,
    "locator must pass the locked Hive Hub skill locator validator"
  );
}

function validateSensitiveCard(config, projectRoot) {
  assert(
    config?.classification === "local-sensitive-locator-plus-unlock",
    "Sensitive card classification must be local-sensitive-locator-plus-unlock"
  );
  assert(config.accessMode === "acl+qr", "Sensitive cards require accessMode acl+qr");
  assert(
    typeof config.cardId === "string" && /^[a-z0-9][a-z0-9-]*$/.test(config.cardId),
    "cardId must contain only lowercase letters, digits, and hyphens"
  );
  assert(typeof config.locator === "string", "locator is required");
  validateLocatorWithSkill(config.locator, projectRoot);
  assert(
    typeof config.unlock === "string" && /^[A-Za-z0-9_-]{43}$/.test(config.unlock),
    "unlock must be canonical unpadded base64url for exactly 32 bytes"
  );
  assert(
    Buffer.from(config.unlock, "base64url").toString("base64url") === config.unlock &&
      Buffer.from(config.unlock, "base64url").length === 32,
    "unlock must be canonical unpadded base64url for exactly 32 bytes"
  );
  assert(
    !("credential" in config) && !("privateKey" in config) && !("token" in config),
    "Repository credentials, private keys, and tokens are not accepted"
  );
}

async function ensureLocalDirectory(projectRoot, outDir) {
  const relative = path.relative(path.resolve(projectRoot), path.resolve(outDir));
  let current = path.resolve(projectRoot);
  for (const segment of relative.split(path.sep)) {
    current = path.join(current, segment);
    try {
      const info = await lstat(current);
      assert(info.isDirectory() && !info.isSymbolicLink(), `Local output ancestor is unsafe: ${current}`);
    } catch (error) {
      if (error.code !== "ENOENT") {
        throw error;
      }
      await mkdir(current, { mode: 0o700 });
    }
  }
}

async function assertSafeOutputFile(filePath) {
  try {
    const info = await lstat(filePath);
    assert(info.isFile() && !info.isSymbolicLink(), `Sensitive card output is unsafe: ${filePath}`);
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }
}

export async function generateSensitiveCard({ config, outDir, projectRoot = process.cwd() }) {
  validateSensitiveCard(config, projectRoot);
  assertLocalOutput(projectRoot, outDir);
  const payload = {
    schema: "hive-hub-qr-join-card/1",
    locator: config.locator,
    unlock_fragment: config.unlock
  };
  const payloadText = canonicalJson(payload).trimEnd();
  const svg = createQrSvg(payloadText, "Q");
  const resolvedOut = path.resolve(outDir);
  await ensureLocalDirectory(projectRoot, resolvedOut);
  const jsonPath = path.join(resolvedOut, `${config.cardId}.json`);
  const svgPath = path.join(resolvedOut, `${config.cardId}.svg`);
  await Promise.all([assertSafeOutputFile(jsonPath), assertSafeOutputFile(svgPath)]);
  await writeFile(jsonPath, `${payloadText}\n`, { mode: 0o600 });
  await writeFile(svgPath, svg, { mode: 0o600 });
  return {
    jsonPath,
    svgPath
  };
}

async function main() {
  const args = parseCliArgs(process.argv.slice(2));
  if (!args.input || !args["out-dir"]) {
    throw new Error(
      "Usage: node scripts/generate-sensitive-card.mjs --input <local-json> --out-dir .hive-hub/private-cards/<name>"
    );
  }
  const config = JSON.parse(await readFile(path.resolve(args.input), "utf8"));
  const result = await generateSensitiveCard({
    config,
    outDir: args["out-dir"]
  });
  process.stdout.write(`Generated local sensitive card at ${result.svgPath}\n`);
}

if (isMain(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 1;
  });
}
