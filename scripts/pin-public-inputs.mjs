import { writeFile } from "node:fs/promises";

import { isMain, parseCliArgs } from "./lib/canonical.mjs";
import { pinPublicInputs } from "./lib/public-inputs.mjs";

async function main() {
  const args = parseCliArgs(process.argv.slice(2));
  if (!args.manifest) {
    throw new Error(
      "Usage: node scripts/pin-public-inputs.mjs --manifest public-manifest.json"
    );
  }
  const result = await pinPublicInputs(args.manifest);
  await writeFile(result.path, result.serialized);
  process.stdout.write(
    `Pinned ${result.manifest.entries.length} explicit public inputs in ${args.manifest}.\n`
  );
}

if (isMain(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 1;
  });
}
