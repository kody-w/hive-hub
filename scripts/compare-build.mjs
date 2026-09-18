import { rm } from "node:fs/promises";
import path from "node:path";

import { buildStaticSurface } from "./build.mjs";
import {
  isMain,
  listPublicFiles,
  parseCliArgs,
  readPublicFile
} from "./lib/canonical.mjs";

export async function compareGeneratedBuild({ manifestPath, root }) {
  const resolvedRoot = path.resolve(root);
  const scratch = path.join(path.dirname(path.resolve(manifestPath)), "tests/.work/reproducible-build");
  await rm(scratch, { force: true, recursive: true });
  try {
    await buildStaticSurface({
      manifestPath,
      outDir: scratch
    });
    const [expectedFiles, actualFiles] = await Promise.all([
      listPublicFiles(resolvedRoot),
      listPublicFiles(scratch)
    ]);
    if (expectedFiles.join("\n") !== actualFiles.join("\n")) {
      throw new Error(
        `Generated file list differs.\nTracked/root:\n${expectedFiles.join("\n")}\nFresh:\n${actualFiles.join("\n")}`
      );
    }
    for (const filePath of expectedFiles) {
      const [expected, actual] = await Promise.all([
        readPublicFile(resolvedRoot, filePath),
        readPublicFile(scratch, filePath)
      ]);
      if (!expected.equals(actual)) {
        throw new Error(`Generated file differs from a fresh deterministic build: ${filePath}`);
      }
    }
    return expectedFiles.length;
  } finally {
    await rm(scratch, { force: true, recursive: true });
  }
}

async function main() {
  const args = parseCliArgs(process.argv.slice(2));
  if (!args.manifest || !args.root) {
    throw new Error(
      "Usage: node scripts/compare-build.mjs --manifest public-manifest.json --root ."
    );
  }
  const count = await compareGeneratedBuild({
    manifestPath: args.manifest,
    root: args.root
  });
  process.stdout.write(`Fresh deterministic build matches ${count} public files.\n`);
}

if (isMain(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 1;
  });
}
