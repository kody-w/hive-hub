import {
  canonicalJson, normalizeRelativePath, publicUrl, sha256Bytes
} from "./canonical.mjs";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function descriptor(filePath, digest, siteBaseUrl) {
  return { path: filePath, ref: `sha256:${digest}`, url: publicUrl(siteBaseUrl, filePath) };
}

export async function writeOrganizationSeeds(writer, entries, { apiPath, siteBaseUrl }) {
  const seeds = new Map();
  for (const entry of entries) {
    const seed = entry.document;
    assert(
      seed.kind === "organization-seed" && seed.schema === "hive-hub-organization-seed/1" &&
      seed.status === "seed-not-activated" && seed.classification === "public-synthetic" &&
      seed.protocol === "rapp-work/1" && seed.workspaceProfile === "rapp-work-sdk/1" &&
      seed.activation?.grantsAuthority === false && /^[a-z0-9-]+$/.test(seed.slug),
      "Invalid public organization seed boundary"
    );
    assert(!seeds.has(entry.declaration.id), "Duplicate organization seed");
    assert(Array.isArray(seed.files) && seed.files.length <= 128, "Invalid seed file inventory");
    const paths = new Set();
    for (const file of seed.files) {
      const normalized = normalizeRelativePath(file.path);
      const bytes = Buffer.from(file.content, "utf8");
      assert(!paths.has(normalized), "Duplicate seed file");
      paths.add(normalized);
      assert(
        bytes.length === file.bytes && sha256Bytes(bytes) === file.sha256,
        "Seed starter file commitment mismatch"
      );
    }
    assert(paths.has("seed.json") && paths.has("initialize.json"), "Seed initialization kit missing");
    assert(seed.files.length === seed.counts.packageFiles, "Seed file count mismatch");
    assert(seed.workspaces.length === seed.counts.workspaces, "Seed workspace count mismatch");
    assert(seed.tasks.length === seed.counts.tasks, "Seed task count mismatch");
    const archiveBytes = Buffer.from(seed.archive.base64, "base64");
    assert(
      archiveBytes.length === seed.archive.bytes &&
      archiveBytes.toString("base64") === seed.archive.base64 &&
      sha256Bytes(archiveBytes) === seed.archive.sha256,
      "Seed archive commitment mismatch"
    );
    const archivePath = `${apiPath}/seeds/downloads/sha256/${seed.archive.sha256.slice(0, 2)}/${seed.archive.sha256}.zip`;
    await writer.write(archivePath, archiveBytes);
    const archive = {
      ...descriptor(archivePath, seed.archive.sha256, siteBaseUrl),
      bytes: archiveBytes.length,
      sha256: seed.archive.sha256,
      mediaType: "application/zip"
    };
    const document = { ...seed, archive };
    const bytes = Buffer.from(canonicalJson(document));
    const digest = sha256Bytes(bytes);
    const filePath = `${apiPath}/seeds/sha256/${digest.slice(0, 2)}/${digest}.json`;
    await writer.write(filePath, bytes);
    seeds.set(entry.declaration.id, {
      id: entry.declaration.id,
      kind: "organization-seed",
      document,
      digest,
      descriptor: descriptor(filePath, digest, siteBaseUrl),
      archive
    });
  }
  return seeds;
}
