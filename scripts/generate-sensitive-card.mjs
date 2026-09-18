import { lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

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

function validateSensitiveCard(config) {
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
  const locator = new URL(config.locator);
  assert(locator.protocol === "https:", "locator must use HTTPS");
  assert(!locator.username && !locator.password, "locator cannot contain repository credentials");
  assert(typeof config.unlock === "string" && config.unlock.length >= 8, "unlock must be at least 8 characters");
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
  validateSensitiveCard(config);
  assertLocalOutput(projectRoot, outDir);
  const payload = {
    accessMode: "acl+qr",
    cardId: config.cardId,
    classification: config.classification,
    locator: config.locator,
    sourceAclRequiredFirst: true,
    unlock: config.unlock,
    v: 1
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
