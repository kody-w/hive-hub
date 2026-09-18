import path from "node:path";

import {
  canonicalJson,
  digestFromRef,
  isMain,
  listPublicFiles,
  parseCliArgs,
  readPublicFile,
  sha256Bytes
} from "./lib/canonical.mjs";
import { loadPublicInputs } from "./lib/public-inputs.mjs";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function readJson(root, filePath) {
  const bytes = await readPublicFile(root, filePath);
  let document;
  try {
    document = JSON.parse(bytes.toString("utf8"));
  } catch (error) {
    throw new Error(`Invalid JSON at ${filePath}: ${error.message}`);
  }
  assert(
    bytes.equals(Buffer.from(canonicalJson(document))),
    `JSON is not canonical UTF-8 with a trailing LF: ${filePath}`
  );
  return { bytes, document };
}

function pathFromInternalUrl(value, manifest) {
  for (const base of [manifest.build.siteBaseUrl, manifest.build.rawBaseUrl]) {
    const normalized = `${base.replace(/\/+$/, "")}/`;
    if (value.startsWith(normalized)) {
      return decodeURIComponent(value.slice(normalized.length).split(/[?#]/, 1)[0]);
    }
  }
  return null;
}

function normalizeLinkedPath(sourcePath, link, manifest) {
  if (
    link.startsWith("mailto:") ||
    link.startsWith("tel:") ||
    link.startsWith("data:") ||
    link === "#"
  ) {
    return null;
  }
  const internal = pathFromInternalUrl(link, manifest);
  if (internal) {
    return internal.endsWith("/") ? `${internal}index.html` : internal;
  }
  if (/^[a-z][a-z0-9+.-]*:/i.test(link) || link.startsWith("//")) {
    return null;
  }
  const withoutFragment = link.split("#", 1)[0].split("?", 1)[0];
  if (!withoutFragment) {
    return null;
  }
  const decoded = decodeURIComponent(withoutFragment);
  const resolved = decoded.startsWith("/")
    ? decoded.slice(1)
    : path.posix.normalize(path.posix.join(path.posix.dirname(sourcePath), decoded));
  return resolved.endsWith("/") ? `${resolved}index.html` : resolved;
}

async function validateDescriptor(root, descriptor, files, manifest, label) {
  assert(typeof descriptor.path === "string", `${label} descriptor has no path`);
  assert(typeof descriptor.ref === "string", `${label} descriptor has no ref`);
  assert(typeof descriptor.url === "string", `${label} descriptor has no URL`);
  assert(files.has(descriptor.path), `${label} target does not exist: ${descriptor.path}`);
  const bytes = await readPublicFile(root, descriptor.path);
  assert(
    digestFromRef(descriptor.ref) === sha256Bytes(bytes),
    `${label} content reference does not match ${descriptor.path}`
  );
  assert(
    pathFromInternalUrl(descriptor.url, manifest) === descriptor.path,
    `${label} URL does not match its path`
  );
}

async function inspectDescriptors(root, value, files, manifest, location = "$") {
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      await inspectDescriptors(root, value[index], files, manifest, `${location}[${index}]`);
    }
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  if (
    typeof value.path === "string" &&
    typeof value.ref === "string" &&
    typeof value.url === "string"
  ) {
    await validateDescriptor(root, value, files, manifest, location);
  }
  if (
    typeof value.path === "string" &&
    typeof value.sha256 === "string" &&
    typeof value.url === "string"
  ) {
    assert(files.has(value.path), `${location} hashed target does not exist: ${value.path}`);
    const bytes = await readPublicFile(root, value.path);
    assert(sha256Bytes(bytes) === value.sha256, `${location} SHA-256 does not match ${value.path}`);
    assert(
      pathFromInternalUrl(value.url, manifest) === value.path,
      `${location} URL does not match ${value.path}`
    );
  }
  for (const [key, child] of Object.entries(value)) {
    await inspectDescriptors(root, child, files, manifest, `${location}.${key}`);
  }
}

function assertNoSensitiveCardFields(value, location = "$") {
  if (Array.isArray(value)) {
    value.forEach((child, index) => assertNoSensitiveCardFields(child, `${location}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    assert(
      !/^(password|privateKey|secret|token|unlock|unlockCommitment)$/i.test(key),
      `Public card contains sensitive key ${location}.${key}`
    );
    assertNoSensitiveCardFields(child, `${location}.${key}`);
  }
}

async function checkHtml(root, filePath, text, files, manifest) {
  assert(/<html\s+lang="en"/i.test(text), `${filePath} has no document language`);
  assert(/<main(?:\s|>)/i.test(text), `${filePath} has no main landmark`);
  assert(/<h1(?:\s|>)/i.test(text), `${filePath} has no h1`);
  assert(
    /http-equiv="Content-Security-Policy"/i.test(text),
    `${filePath} has no Content Security Policy`
  );
  assert(
    /<meta\s+name="referrer"\s+content="no-referrer">/i.test(text),
    `${filePath} has no no-referrer policy`
  );
  assert(!/<style(?:\s|>)/i.test(text), `${filePath} contains inline style`);
  assert(!/<script(?![^>]*\bsrc=)[^>]*>/i.test(text), `${filePath} contains inline script`);
  for (const image of text.matchAll(/<img\b([^>]*)>/gi)) {
    assert(/\balt="[^"]*"/i.test(image[1]), `${filePath} contains an image without alt text`);
  }
  for (const match of text.matchAll(/\b(?:href|src)="([^"]+)"/gi)) {
    const linkedPath = normalizeLinkedPath(filePath, match[1], manifest);
    if (linkedPath) {
      assert(files.has(linkedPath), `${filePath} has broken link ${match[1]} -> ${linkedPath}`);
    }
  }
}

async function validateReceiptChain(root, receiptIndex) {
  assert(receiptIndex.appendOnly === true, "Receipt index is not append-only");
  let previous = null;
  for (let index = 0; index < receiptIndex.receipts.length; index += 1) {
    const descriptor = receiptIndex.receipts[index];
    const receipt = (await readJson(root, descriptor.path)).document;
    assert(receipt.sequence === index + 1, `Receipt sequence is broken at ${descriptor.path}`);
    if (previous === null) {
      assert(receipt.previous === null, "First receipt must have a null previous link");
    } else {
      assert(
        receipt.previous?.ref === previous.ref &&
          receipt.previous?.path === previous.path &&
          receipt.previous?.url === previous.url,
        `Receipt ${descriptor.path} does not link to its immutable predecessor`
      );
    }
    previous = descriptor;
  }
  assert(
    (previous === null && receiptIndex.head === null) ||
      (receiptIndex.head?.ref === previous?.ref && receiptIndex.head?.path === previous?.path),
    "Receipt head does not match the final receipt"
  );
}

export async function checkStaticSurface({ root, manifestPath }) {
  const resolvedRoot = path.resolve(root);
  const loaded = await loadPublicInputs(manifestPath);
  const { manifest } = loaded;
  const fileList = await listPublicFiles(resolvedRoot);
  const files = new Set(fileList);
  const requiredFiles = [
    ".nojekyll",
    ".well-known/hive-hub.json",
    "api/hive-hub/v1/index.json",
    "api/hive-hub/v1/dialbook.json",
    "api/hive-hub/v1/buckets/index.json",
    "api/hive-hub/v1/federation/index.json",
    "api/hive-hub/v1/federation/buckets.json",
    "api/hive-hub/v1/cards/index.json",
    "api/hive-hub/v1/hashes.json",
    "api/hive-hub/v1/offline-seed.json",
    "api/hive-hub/v1/receipts/index.json",
    "api/hive-hub/v1/status.json",
    "hub/index.html",
    "hub/join/index.html",
    "hub/join/join.js",
    "hub/join/ai.json",
    "llms.txt"
  ];
  for (const required of requiredFiles) {
    assert(files.has(required), `Required public file is missing: ${required}`);
  }

  const hashes = (await readJson(resolvedRoot, manifest.build.apiPath + "/hashes.json")).document;
  assert(hashes.kind === "hash-manifest" && hashes.algorithm === "sha256", "Invalid hash manifest");
  assert(hashes.build.policy === "explicit-public-only-v1", "Public input policy is not recorded");
  assert(hashes.build.privateBooksInspected === 0, "Build reports private-book inspection");
  assert(
    hashes.build.inspectedInputCount === manifest.entries.length,
    "Hash manifest input audit count is incomplete"
  );
  const expectedHashedFiles = fileList.filter(
    (filePath) => filePath !== manifest.build.apiPath + "/hashes.json"
  );
  assert(
    Object.keys(hashes.files).sort().join("\n") === expectedHashedFiles.join("\n"),
    "Hash manifest file set does not exactly match the public output"
  );
  for (const [filePath, expected] of Object.entries(hashes.files)) {
    const bytes = await readPublicFile(resolvedRoot, filePath);
    assert(expected.bytes === bytes.length, `Byte count mismatch for ${filePath}`);
    assert(expected.sha256 === sha256Bytes(bytes), `Hash mismatch for ${filePath}`);
  }

  const jsonDocuments = new Map();
  for (const filePath of fileList.filter((candidate) => candidate.endsWith(".json"))) {
    const parsed = await readJson(resolvedRoot, filePath);
    jsonDocuments.set(filePath, parsed.document);
    await inspectDescriptors(resolvedRoot, parsed.document, files, manifest, filePath);
  }

  for (const filePath of fileList.filter((candidate) => candidate.endsWith(".html"))) {
    const text = (await readPublicFile(resolvedRoot, filePath)).toString("utf8");
    await checkHtml(resolvedRoot, filePath, text, files, manifest);
  }

  const runtimeText = (
    await Promise.all(
      fileList
        .filter((candidate) => /\.(?:html|js)$/.test(candidate))
        .map(async (candidate) => (await readPublicFile(resolvedRoot, candidate)).toString("utf8"))
    )
  ).join("\n");
  for (const forbidden of [
    /\blocalStorage\b/,
    /\bsessionStorage\b/,
    /\bindexedDB\b/,
    /\bserviceWorker\b/,
    /\bsendBeacon\b/,
    /\bdocument\.cookie\b/,
    /google-analytics/i,
    /segment\.com/i
  ]) {
    assert(!forbidden.test(runtimeText), `Runtime contains prohibited capability ${forbidden}`);
  }
  assert(!/<script[^>]+src="https?:/i.test(runtimeText), "Runtime loads an external script");

  const allPublicText = (
    await Promise.all(
      fileList.map(async (candidate) => (await readPublicFile(resolvedRoot, candidate)).toString("utf8"))
    )
  ).join("\n");
  assert(!/microsol/i.test(allPublicText), "Public output names prohibited private-network material");
  assert(!/\bRAPP\b/.test(allPublicText), "Generic public output claims or names ecosystem authority");

  const joinScript = (await readPublicFile(resolvedRoot, "hub/join/join.js")).toString("utf8");
  const capturePosition = joinScript.indexOf("const capturedFragment = window.location.hash;");
  const clearPosition = joinScript.indexOf("window.history.replaceState");
  const networkPosition = joinScript.indexOf("void verifyAndRender");
  assert(capturePosition >= 0, "Join runtime does not capture the fragment");
  assert(
    clearPosition > capturePosition && clearPosition < networkPosition,
    "Join runtime does not clear the fragment before verification or network access"
  );

  const qrFiles = fileList.filter((candidate) => candidate.endsWith(".svg"));
  assert(qrFiles.length > 0, "Build generated no QR SVG");
  for (const qrPath of qrFiles) {
    const svg = (await readPublicFile(resolvedRoot, qrPath)).toString("utf8");
    assert(
      /<svg[^>]+xmlns="http:\/\/www\.w3\.org\/2000\/svg"/i.test(svg),
      `${qrPath} is not a standard SVG`
    );
    assert(!/<script/i.test(svg) && !/\bhref=/i.test(svg), `${qrPath} contains active or remote content`);
  }

  const dialbook = jsonDocuments.get(`${manifest.build.apiPath}/dialbook.json`);
  assert(dialbook.kind === "public-dialbook", "Dialbook kind is invalid");
  for (const [chant, candidates] of Object.entries(dialbook.chants)) {
    assert(Array.isArray(candidates) && candidates.length > 0, `Chant ${chant} is not a candidate array`);
  }
  assert(
    dialbook.candidateSemantics.includes("no candidate is unique authority"),
    "Dialbook does not bound chant authority"
  );

  const recordDescriptor = dialbook.records[0];
  const record = jsonDocuments.get(recordDescriptor.path);
  assert(record.kind === "dial-record" && record.visibility === "public", "Example record is not public");
  assert(
    record.locator.repositoryUrl ===
      "https://github.com/billwhalenmsft/softwarecoellc-vteam-hive",
    "Example record repository is incorrect"
  );
  assert(
    record.locator.revision === "f66da3d879b53a439bc87de764d79f68ceec048a",
    "Example record commit is not pinned as required"
  );
  assert(record.claims.authority.length === 0, "Example record claims authority");
  assert(
    record.claims.semanticCompatibility.length === 0,
    "Example record claims semantic compatibility"
  );
  const protocol = jsonDocuments.get(record.protocol.path);
  assert(
    protocol.protocolId === "urn:hive-hub:protocol:github-repository:1",
    "Example does not use the generic GitHub repository protocol"
  );
  assert(record.protocolFingerprint === record.protocol.ref, "Protocol fingerprint is not exact");

  const bucketDirectory = jsonDocuments.get(`${manifest.build.apiPath}/buckets/index.json`);
  assert(bucketDirectory.buckets.length >= 2, "Static API does not expose multiple buckets");
  const routedRecords = bucketDirectory.buckets.flatMap((bucket) => {
    const bucketIndex = jsonDocuments.get(bucket.index.path);
    return bucketIndex.records.map((entry) => entry.ref);
  });
  assert(
    routedRecords.sort().join("\n") === dialbook.records.map((entry) => entry.ref).sort().join("\n"),
    "Bucket shards do not cover the public dialbook exactly"
  );

  const federation = jsonDocuments.get(`${manifest.build.apiPath}/federation/index.json`);
  assert(
    federation.candidateSemantics === "union-without-authority",
    "Federation index creates authority"
  );
  const federationBuckets = jsonDocuments.get(`${manifest.build.apiPath}/federation/buckets.json`);
  for (const candidates of Object.values(federationBuckets.routes)) {
    assert(Array.isArray(candidates), "Federation bucket route is not a candidate array");
  }

  const cardsIndex = jsonDocuments.get(`${manifest.build.apiPath}/cards/index.json`);
  for (const cardEntry of cardsIndex.cards) {
    assert(
      cardEntry.classification === "public-locator-only",
      "Public card index contains a non-public card"
    );
    const card = jsonDocuments.get(cardEntry.card.path);
    assert(card.classification === "public-locator-only", "Card is not locator-only");
    assertNoSensitiveCardFields(card, cardEntry.card.path);
  }

  const offlineSeed = jsonDocuments.get(`${manifest.build.apiPath}/offline-seed.json`);
  for (const [reference, document] of Object.entries(offlineSeed.objects)) {
    assert(
      sha256Bytes(Buffer.from(canonicalJson(document))) === digestFromRef(reference),
      `Offline seed object does not match ${reference}`
    );
    assert(typeof offlineSeed.routes[reference] === "string", `Offline seed has no route for ${reference}`);
  }

  await validateReceiptChain(
    resolvedRoot,
    jsonDocuments.get(`${manifest.build.apiPath}/receipts/index.json`)
  );

  for (const filePath of fileList.filter((candidate) => candidate.includes("/sha256/"))) {
    const match = /\/sha256\/(?:[^/]+\/)?([a-f0-9]{64})\.json$/.exec(filePath);
    if (match) {
      const bytes = await readPublicFile(resolvedRoot, filePath);
      assert(sha256Bytes(bytes) === match[1], `Content-addressed path is mutable: ${filePath}`);
    }
  }

  return {
    fileCount: fileList.length,
    immutableObjectCount: fileList.filter((candidate) => candidate.includes("/sha256/")).length,
    inputCount: loaded.entries.length,
    qrCount: qrFiles.length
  };
}

async function main() {
  const args = parseCliArgs(process.argv.slice(2));
  if (!args.root || !args.manifest) {
    throw new Error(
      "Usage: node scripts/check.mjs --root <public-root> --manifest public-manifest.json"
    );
  }
  const result = await checkStaticSurface({
    manifestPath: args.manifest,
    root: args.root
  });
  process.stdout.write(
    `Checked ${result.fileCount} public files, ${result.immutableObjectCount} immutable objects, ${result.qrCount} QR SVG, and ${result.inputCount} explicit inputs.\n`
  );
}

if (isMain(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 1;
  });
}
