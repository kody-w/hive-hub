import { lstat, readFile, realpath } from "node:fs/promises";
import path from "node:path";

import {
  canonicalJson,
  normalizeRelativePath,
  sha256Bytes,
  sha256Json,
  toPosixRelative
} from "./canonical.mjs";

const ALLOWED_KINDS = new Set([
  "adapter",
  "conformance",
  "core-card",
  "core-schema",
  "learning-bundle",
  "protocol",
  "receipt",
  "release",
  "record",
  "skill-declaration"
]);

const FORBIDDEN_SOURCE_SEGMENTS = new Set([
  ".hive-hub",
  "private",
  "private-books",
  "secrets"
]);

function assertObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be a JSON object`);
  }
}

function assertHttpsUrl(value, label) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${label} must be a valid URL`);
  }
  if (parsed.protocol !== "https:" || parsed.username || parsed.password || parsed.hash) {
    throw new Error(`${label} must be a credential-free HTTPS URL without a fragment`);
  }
}

function validateManifestShape(manifest) {
  assertObject(manifest, "Public manifest");
  if (manifest.manifestVersion !== "1.0.0") {
    throw new Error("Public manifest must use manifestVersion 1.0.0");
  }
  if (manifest.classification !== "public-only") {
    throw new Error("Public build requires classification public-only");
  }
  if (manifest.sourceRoot !== "public-src") {
    throw new Error("Public build sourceRoot must be exactly public-src");
  }
  if (manifest.productVersion !== "0.1.0") {
    throw new Error("Public manifest must bind productVersion 0.1.0");
  }
  assertObject(manifest.build, "manifest.build");
  if (manifest.build.apiPath !== "api/hive-hub/v1") {
    throw new Error("manifest.build.apiPath must be api/hive-hub/v1");
  }
  if (Number.isNaN(Date.parse(manifest.build.generatedAt))) {
    throw new Error("manifest.build.generatedAt must be an ISO timestamp");
  }
  assertHttpsUrl(manifest.build.siteBaseUrl, "manifest.build.siteBaseUrl");
  assertHttpsUrl(manifest.build.rawBaseUrl, "manifest.build.rawBaseUrl");
  if (!Array.isArray(manifest.entries) || manifest.entries.length === 0) {
    throw new Error("Public manifest must explicitly list entries");
  }
  if (!Array.isArray(manifest.buckets) || manifest.buckets.length < 2) {
    throw new Error("Public manifest must define multiple buckets");
  }
  if (!Array.isArray(manifest.cards) || manifest.cards.length === 0) {
    throw new Error("Public manifest must explicitly list public cards");
  }
  assertObject(manifest.federation, "manifest.federation");
  if (!Array.isArray(manifest.federation.members)) {
    throw new Error("manifest.federation.members must be an array");
  }

  const ids = new Set();
  const paths = new Set();
  for (const entry of manifest.entries) {
    assertObject(entry, "manifest entry");
    if (entry.classification !== "public") {
      throw new Error(`Manifest entry ${entry.id ?? "(unknown)"} is not explicitly public`);
    }
    if (typeof entry.id !== "string" || entry.id.length === 0 || ids.has(entry.id)) {
      throw new Error(`Manifest entry id is missing or duplicated: ${entry.id}`);
    }
    ids.add(entry.id);
    if (!ALLOWED_KINDS.has(entry.kind)) {
      throw new Error(`Unsupported public entry kind: ${entry.kind}`);
    }
    const normalized = normalizeRelativePath(entry.path);
    const segments = normalized.split("/").map((segment) => segment.toLowerCase());
    if (segments.some((segment) => FORBIDDEN_SOURCE_SEGMENTS.has(segment))) {
      throw new Error(`Public entry path uses a forbidden source segment: ${entry.path}`);
    }
    if (paths.has(normalized)) {
      throw new Error(`Manifest entry path is duplicated: ${normalized}`);
    }
    paths.add(normalized);
    if (typeof entry.sha256 !== "string") {
      throw new Error(`Manifest entry ${entry.id} has no SHA-256 pin`);
    }
  }

  const ranges = [...manifest.buckets].sort((left, right) =>
    left.minimum.localeCompare(right.minimum)
  );
  let expected = 0;
  const bucketIds = new Set();
  for (const bucket of ranges) {
    assertObject(bucket, "bucket");
    if (
      typeof bucket.id !== "string" ||
      bucketIds.has(bucket.id) ||
      !/^[a-z0-9-]+$/.test(bucket.id)
    ) {
      throw new Error(`Bucket id is invalid or duplicated: ${bucket.id}`);
    }
    bucketIds.add(bucket.id);
    if (!/^[a-f0-9]{2}$/.test(bucket.minimum) || !/^[a-f0-9]{2}$/.test(bucket.maximum)) {
      throw new Error(`Bucket ${bucket.id} bounds must be two lowercase hexadecimal digits`);
    }
    const minimum = Number.parseInt(bucket.minimum, 16);
    const maximum = Number.parseInt(bucket.maximum, 16);
    if (minimum !== expected || maximum < minimum) {
      throw new Error(`Bucket ${bucket.id} does not continue the complete byte range`);
    }
    expected = maximum + 1;
  }
  if (expected !== 256) {
    throw new Error("Buckets must cover every SHA-256 first-byte value exactly once");
  }

  for (const card of manifest.cards) {
    assertObject(card, "card");
    if (!ids.has(card.recordId)) {
      throw new Error(`Card ${card.cardId} references unknown record ${card.recordId}`);
    }
    if (!/^[a-z0-9-]+$/.test(card.slug)) {
      throw new Error(`Card slug is not URL-safe: ${card.slug}`);
    }
  }

  for (const member of manifest.federation.members) {
    assertObject(member, "federation member");
    assertHttpsUrl(member.indexUrl, `federation member ${member.hubId} indexUrl`);
  }
}

async function readManifestFile(manifestPath) {
  const absoluteManifestPath = path.resolve(manifestPath);
  if (path.basename(absoluteManifestPath) !== "public-manifest.json") {
    throw new Error("Public builds require an explicit public-manifest.json");
  }
  const manifestInfo = await lstat(absoluteManifestPath);
  if (!manifestInfo.isFile() || manifestInfo.isSymbolicLink()) {
    throw new Error("public-manifest.json must be a regular non-symlink file");
  }
  const manifestBytes = await readFile(absoluteManifestPath);
  let manifest;
  try {
    manifest = JSON.parse(manifestBytes);
  } catch (error) {
    throw new Error(`Cannot parse public manifest: ${error.message}`);
  }
  validateManifestShape(manifest);
  return {
    absoluteManifestPath,
    manifest,
    manifestBytes
  };
}

async function assertPlainPublicRoot(rootPath) {
  const rootInfo = await lstat(rootPath);
  if (!rootInfo.isDirectory() || rootInfo.isSymbolicLink()) {
    throw new Error("public-src must be a real directory, not a symlink");
  }
  return realpath(rootPath);
}

function resolvePublicInput(rootPath, entryPath) {
  const normalized = normalizeRelativePath(entryPath);
  const resolved = path.resolve(rootPath, ...normalized.split("/"));
  if (!resolved.startsWith(`${path.resolve(rootPath)}${path.sep}`)) {
    throw new Error(`Public input escapes public-src: ${entryPath}`);
  }
  return { normalized, resolved };
}

export async function loadPublicInputs(manifestPath, options = {}) {
  const { requirePins = true } = options;
  const { absoluteManifestPath, manifest, manifestBytes } = await readManifestFile(manifestPath);
  const manifestDirectory = path.dirname(absoluteManifestPath);
  const sourceRoot = path.resolve(manifestDirectory, manifest.sourceRoot);
  const realSourceRoot = await assertPlainPublicRoot(sourceRoot);
  const entries = [];
  const inspectedInputs = [];

  for (const declaration of manifest.entries) {
    const { normalized, resolved } = resolvePublicInput(sourceRoot, declaration.path);
    const inputInfo = await lstat(resolved);
    if (!inputInfo.isFile() || inputInfo.isSymbolicLink()) {
      throw new Error(`Public input must be a regular non-symlink file: ${normalized}`);
    }
    const realInput = await realpath(resolved);
    if (!realInput.startsWith(`${realSourceRoot}${path.sep}`)) {
      throw new Error(`Public input resolves outside public-src: ${normalized}`);
    }
    const bytes = await readFile(realInput);
    const digest = sha256Bytes(bytes);
    if (requirePins && !/^[a-f0-9]{64}$/.test(declaration.sha256)) {
      throw new Error(`Public input ${normalized} is not pinned; run npm run pin:public`);
    }
    if (requirePins && digest !== declaration.sha256) {
      throw new Error(
        `Public input pin mismatch for ${normalized}: expected ${declaration.sha256}, got ${digest}`
      );
    }
    let document;
    try {
      document = JSON.parse(bytes);
    } catch (error) {
      throw new Error(`Cannot parse public input ${normalized}: ${error.message}`);
    }
    assertObject(document, `Public input ${normalized}`);
    entries.push({
      bytes,
      declaration,
      digest,
      document,
      path: normalized
    });
    inspectedInputs.push({
      classification: "public",
      path: path.posix.join(manifest.sourceRoot, normalized),
      sha256: digest
    });
  }

  return {
    audit: {
      inspectedInputCount: inspectedInputs.length,
      inspectedInputs,
      manifest: toPosixRelative(manifestDirectory, absoluteManifestPath),
      manifestCanonicalSha256: sha256Json(manifest),
      manifestFileSha256: sha256Bytes(manifestBytes),
      policy: "explicit-public-only-v1",
      sourceRoot: manifest.sourceRoot
    },
    entries,
    manifest,
    manifestDirectory
  };
}

export async function pinPublicInputs(manifestPath) {
  const loaded = await loadPublicInputs(manifestPath, { requirePins: false });
  const pins = new Map(loaded.entries.map((entry) => [entry.declaration.id, entry.digest]));
  for (const entry of loaded.manifest.entries) {
    entry.sha256 = pins.get(entry.id);
  }
  return {
    manifest: loaded.manifest,
    path: path.resolve(manifestPath),
    serialized: canonicalJson(loaded.manifest)
  };
}
