import assert from "node:assert/strict";
import { chmod, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import test, { after, before } from "node:test";
import { fileURLToPath } from "node:url";

import { buildStaticSurface } from "../scripts/build.mjs";
import { checkStaticSurface } from "../scripts/check.mjs";
import { generateSensitiveCard } from "../scripts/generate-sensitive-card.mjs";
import {
  canonicalJson,
  listPublicFiles,
  readPublicFile,
  sha256Bytes
} from "../scripts/lib/canonical.mjs";
import { loadPublicInputs } from "../scripts/lib/public-inputs.mjs";

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifestPath = path.join(repository, "public-manifest.json");
const work = path.join(repository, "tests/.work/node-test");
const buildA = path.join(work, "build-a");
const buildB = path.join(work, "build-b");
let resultA;

before(async () => {
  await rm(work, { force: true, recursive: true });
  await mkdir(work, { recursive: true });
  resultA = await buildStaticSurface({
    manifestPath,
    outDir: buildA
  });
});

after(async () => {
  await rm(work, { force: true, recursive: true });
});

test("build is byte-for-byte deterministic", async () => {
  const resultB = await buildStaticSurface({
    manifestPath,
    outDir: buildB
  });
  assert.deepEqual(resultA.files, resultB.files);
  const files = await listPublicFiles(buildA);
  for (const filePath of files) {
    const [left, right] = await Promise.all([
      readPublicFile(buildA, filePath),
      readPublicFile(buildB, filePath)
    ]);
    assert.ok(left.equals(right), `${filePath} differs across builds`);
  }
});

test("generated surface passes links, hashes, security, and accessibility gates", async () => {
  const result = await checkStaticSurface({
    manifestPath,
    root: buildA
  });
  assert.equal(result.inputCount, 6);
  assert.ok(result.immutableObjectCount >= 6);
  assert.equal(result.qrCount, 1);
});

test("example record is exact and grants no authority or semantic compatibility", async () => {
  const record = resultA.records[0].document;
  assert.equal(
    record.locator.repositoryUrl,
    "https://github.com/billwhalenmsft/softwarecoellc-vteam-hive"
  );
  assert.equal(record.locator.revision, "f66da3d879b53a439bc87de764d79f68ceec048a");
  assert.deepEqual(record.claims.authority, []);
  assert.deepEqual(record.claims.semanticCompatibility, []);
  assert.equal(record.protocolFingerprint, record.protocol.ref);
});

test("public build input reader never scans adjacent private books", async () => {
  const fixtureRoot = path.join(work, "isolation");
  const publicRoot = path.join(fixtureRoot, "public-src");
  const privateRoot = path.join(fixtureRoot, "private-books");
  await Promise.all([
    mkdir(publicRoot, { recursive: true }),
    mkdir(privateRoot, { recursive: true })
  ]);
  const publicBytes = Buffer.from(canonicalJson({ visibility: "public" }));
  const privatePath = path.join(privateRoot, "private-book.json");
  await Promise.all([
    writeFile(path.join(publicRoot, "record.json"), publicBytes),
    writeFile(privatePath, '{"sentinel":"must-not-be-read"}\n')
  ]);
  await chmod(privatePath, 0o000);
  const fixtureManifestPath = path.join(fixtureRoot, "public-manifest.json");
  const fixtureManifest = {
    build: {
      apiPath: "api/hive-hub/v1",
      generatedAt: "2026-09-18T19:16:11Z",
      rawBaseUrl: "https://example.test/raw",
      siteBaseUrl: "https://example.test/hub"
    },
    buckets: [
      { id: "sha256-00-7f", maximum: "7f", minimum: "00" },
      { id: "sha256-80-ff", maximum: "ff", minimum: "80" }
    ],
    cards: [
      {
        cardId: "fixture-card",
        chant: "fixture",
        recordId: "fixture-record",
        slug: "fixture",
        title: "Fixture"
      }
    ],
    classification: "public-only",
    entries: [
      {
        classification: "public",
        id: "fixture-record",
        kind: "record",
        path: "record.json",
        sha256: sha256Bytes(publicBytes)
      }
    ],
    federation: { members: [] },
    manifestVersion: "1.0.0",
    sourceRoot: "public-src"
  };
  await writeFile(fixtureManifestPath, canonicalJson(fixtureManifest));
  try {
    const loaded = await loadPublicInputs(fixtureManifestPath);
    assert.deepEqual(
      loaded.audit.inspectedInputs.map((entry) => entry.path),
      ["public-src/record.json"]
    );

    fixtureManifest.entries[0].path = "../private-books/private-book.json";
    await writeFile(fixtureManifestPath, canonicalJson(fixtureManifest));
    await assert.rejects(
      loadPublicInputs(fixtureManifestPath),
      /Path escapes its root/,
      "A private-book traversal must fail before any input read"
    );
  } finally {
    await chmod(privatePath, 0o600);
  }
});

test("public QR envelope is locator-only and sensitive cards stay local", async () => {
  const publicEnvelope = resultA.cards[0].envelope;
  assert.deepEqual(Object.keys(publicEnvelope).sort(), ["card", "sha256", "v"]);
  assert.equal(publicEnvelope.v, 1);

  const localOut = path.join(work, "sensitive");
  const local = await generateSensitiveCard({
    config: {
      accessMode: "acl+qr",
      cardId: "local-test-card",
      classification: "local-sensitive-locator-plus-unlock",
      locator: "https://example.test/private-candidate",
      unlock: "test-only-unlock"
    },
    outDir: localOut,
    projectRoot: repository
  });
  const [json, svg] = await Promise.all([
    readFile(local.jsonPath, "utf8"),
    readFile(local.svgPath, "utf8")
  ]);
  assert.match(json, /test-only-unlock/);
  assert.match(svg, /xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
  assert.ok(!resultA.files.some((filePath) => filePath.includes("sensitive")));

  await assert.rejects(
    generateSensitiveCard({
      config: {
        accessMode: "acl+qr",
        cardId: "must-fail",
        classification: "local-sensitive-locator-plus-unlock",
        locator: "https://example.test/private-candidate",
        unlock: "test-only-unlock"
      },
      outDir: path.join(repository, "hub/private-card"),
      projectRoot: repository
    }),
    /Sensitive cards may be written only/
  );
});
