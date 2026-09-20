import assert from "node:assert/strict";
import { execFile, spawnSync } from "node:child_process";
import { webcrypto } from "node:crypto";
import { chmod, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import path from "node:path";
import test, { after, before } from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import vm from "node:vm";

import { buildStaticSurface } from "../scripts/build.mjs";
import { checkStaticSurface } from "../scripts/check.mjs";
import { generateSensitiveCard } from "../scripts/generate-sensitive-card.mjs";
import {
  CHANT_PROTOCOL,
  CHANT_VOCABULARY_SHA256,
  deriveChant,
  normalizeChant
} from "../scripts/lib/chant.mjs";
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

test("committed public records share the core identity body and derived chant", async () => {
  const dialbook = JSON.parse(
    await readFile(path.join(repository, "api/hive-hub/v1/dialbook.json"), "utf8")
  );
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  assert.ok(dialbook.records.length > 0);
  assert.equal(
    dialbook.records.length,
    manifest.entries.filter((entry) => entry.kind === "record").length
  );
  for (const descriptor of dialbook.records) {
    const bytes = await readFile(path.join(repository, descriptor.path));
    const record = JSON.parse(bytes);
    const core = record.coreRecord;
    assert.ok(core, `${descriptor.path} has no coreRecord`);
    assert.deepEqual(Object.keys(core).sort(), [
      "adapter_registration_address", "chants", "description", "id", "kind",
      "learning_bundle_address", "name", "protocol_fingerprint", "schema_version",
      "urls", "visibility"
    ]);
    assert.equal(core.kind, "dial-record");
    assert.equal(core.schema_version, 1);
    const { id, ...fields } = core;
    const body = { ...fields, kind: "dial-record-body" };
    const digest = sha256Bytes(Buffer.from(canonicalJson(body).slice(0, -1)));
    assert.equal(id, `urn:hivehub:sha256:${digest}`);
    assert.equal(record.dialId, `dial:sha256:${digest}`);
    assert.deepEqual(record.chants, [
      { role: "candidate-locator-only", value: deriveChant(record.dialId) }
    ]);
    assert.equal(descriptor.ref, `sha256:${sha256Bytes(bytes)}`);
    assert.equal(bytes.toString("utf8"), canonicalJson(record));
  }
  const emitted = (await listPublicFiles(repository))
    .filter((file) => file.startsWith("api/hive-hub/v1/records/sha256/"));
  const accounted = new Set(dialbook.records.map((descriptor) => descriptor.path));
  for (const entry of manifest.entries.filter((item) => item.kind === "historical-object")) {
    const bytes = await readFile(path.join(repository, "public-src", entry.path));
    if (JSON.parse(bytes).kind !== "dial-record") {
      continue;
    }
    assert.equal(sha256Bytes(bytes), entry.sha256);
    const archived = emitted.filter((file) => file.endsWith(`/${entry.sha256}.json`));
    assert.equal(archived.length, 1);
    assert.deepEqual(await readFile(path.join(repository, archived[0])), bytes);
    accounted.add(archived[0]);
  }
  assert.deepEqual(emitted.sort(), [...accounted].sort());
});

test("generated surface passes links, hashes, security, and accessibility gates", async () => {
  const result = await checkStaticSurface({
    manifestPath,
    root: buildA
  });
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  assert.equal(result.inputCount, manifest.entries.length);
  assert.ok(result.immutableObjectCount >= 9);
  assert.equal(result.qrCount, 22);
});

test("published camera cards use their record's canonical locator and keep legacy cards separate", async () => {
  for (const card of resultA.cards) {
    const webCard = JSON.parse(await readFile(path.join(buildA, card.descriptor.path), "utf8"));
    const coreCardBytes = await readFile(path.join(buildA, card.cameraAiCard.path));
    const coreCard = JSON.parse(coreCardBytes);
    const record = JSON.parse(await readFile(path.join(buildA, webCard.record.path), "utf8"));
    assert.equal(coreCard.locator, record.dialId);
    assert.equal(coreCard.locator, webCard.dialId);
    assert.equal(webCard.dialId, record.coreRecord.id.replace(/^urn:hivehub:/, "dial:"));
    assert.equal(card.cameraAiCard.ref, `sha256:${sha256Bytes(coreCardBytes)}`);
    assert.equal(card.cameraEnvelope.sha256, sha256Bytes(coreCardBytes));
    const { card_id, ...fields } = coreCard;
    assert.equal(
      card_id,
      `urn:hivehub:sha256:${sha256Bytes(
        Buffer.from(canonicalJson({ ...fields, kind: "ai-join-card-body" }).slice(0, -1))
      )}`
    );
    const legacy = JSON.parse(await readFile(path.join(buildA, webCard.legacySkillCard.path)));
    assert.equal(legacy.locator, webCard.legacySkillDialId);
    assert.notEqual(legacy.locator, coreCard.locator);
  }
});

test("CI HTTP smoke passes against the generated site on an ephemeral port", async () => {
  const files = new Map(await Promise.all(resultA.files.map(async (file) => [
    "/" + file, await readFile(path.join(buildA, file))
  ])));
  const server = createServer((request, response) => {
    const pathname = new URL(request.url, "http://127.0.0.1/").pathname;
    const file = pathname.endsWith("/") ? pathname + "index.html" : pathname;
    const bytes = files.get(file);
    response.writeHead(bytes ? 200 : 404, {
      "Content-Type": file.endsWith(".json") ? "application/json" : "text/html"
    });
    response.end(bytes);
  });
  try {
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", resolve);
    });
    const address = server.address();
    assert.ok(address && typeof address !== "string");
    const result = await promisify(execFile)(
      process.execPath,
      [path.join(repository, "scripts/smoke-http.mjs"), "--base", `http://127.0.0.1:${address.port}/`],
      { timeout: 30_000 }
    );
    assert.equal(result.stderr, "");
    assert.equal(result.stdout, "local HTTP static smoke passed\n");
  } finally {
    server.closeAllConnections();
    await new Promise((resolve, reject) => {
      server.close((error) => error ? reject(error) : resolve());
    });
  }
});

test("example record is exact and grants no authority or semantic compatibility", async () => {
  const record = resultA.records[0].document;
  assert.equal(
    record.locator.repositoryUrl,
    "https://github.com/kody-w/hive-hub"
  );
  assert.equal(record.locator.revision, "8e9ee55a7eb9fe4b4aaa084290e1916c0edcade9");
  assert.deepEqual(record.claims.authority, []);
  assert.deepEqual(record.claims.semanticCompatibility, []);
  assert.equal(record.protocolFingerprint, record.protocol.ref);
  assert.equal(
    record.dialId,
    record.coreRecord.id.replace(/^urn:hivehub:/, "dial:")
  );
  assert.equal(record.chants[0].value, deriveChant(record.dialId));
  assert.deepEqual(record.aliases, ["hive-hub-public-lab"]);
  assert.notEqual(record.chants[0].value, record.aliases[0]);
  const chantProtocol = JSON.parse(
    await readFile(path.join(buildA, record.chantProtocol.path), "utf8")
  );
  assert.equal(chantProtocol.protocolName, CHANT_PROTOCOL);
  assert.equal(chantProtocol.vocabulary.sha256, CHANT_VOCABULARY_SHA256);
  assert.deepEqual(chantProtocol.requires, {
    rappIdentity: false,
    rappRuntime: false
  });
});

test("hive-hub-chant/1 is exact, human-friendly, and protocol-neutral", () => {
  const dialId =
    "dial:sha256:6b822d070281ee28b89c3c4209e5ba6e796a09ec5973da6e73324cee44127c32";
  assert.equal(CHANT_PROTOCOL, "hive-hub-chant/1");
  assert.equal(
    CHANT_VOCABULARY_SHA256,
    "325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36"
  );
  assert.equal(
    normalizeChant("JUNIPER QUARTZ HARBOR BIRCH COBALT NOOK FLINT"),
    deriveChant(dialId)
  );
  assert.throws(() => normalizeChant("hive-hub-public-lab"));
});

test("public laboratory preserves prior receipts and appends the camera-card correction", async () => {
  const index = JSON.parse(
    await readFile(path.join(buildA, "api/hive-hub/v1/receipts/index.json"), "utf8")
  );
  assert.equal(index.receipts.length, 3);
  const receipt = JSON.parse(
    await readFile(path.join(buildA, index.receipts[0].path), "utf8")
  );
  assert.equal(receipt.event, "publish-record");
  assert.equal(receipt.previous, null);
  const migration = JSON.parse(
    await readFile(path.join(buildA, index.receipts[1].path), "utf8")
  );
  assert.deepEqual(migration.previous, index.receipts[0]);
  assert.deepEqual(migration.subject, resultA.records[0].descriptor);
  assert.notDeepEqual(receipt.subject, migration.subject);
  const correction = JSON.parse(
    await readFile(path.join(buildA, index.receipts[2].path), "utf8")
  );
  assert.deepEqual(correction.previous, index.receipts[1]);
  assert.deepEqual(correction.subject, migration.subject);
  assert.deepEqual(correction.card, resultA.cards[0].descriptor);
  assert.notDeepEqual(correction.card, migration.card);
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
    productVersion: "0.1.1",
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
  const cameraEnvelope = resultA.cards[0].cameraEnvelope;
  assert.deepEqual(Object.keys(cameraEnvelope).sort(), ["card", "sha256", "v"]);
  assert.equal(cameraEnvelope.v, 1);
  assert.match(resultA.cards[0].cameraQrFragment, /^#v1\.[A-Za-z0-9_-]+$/);

  const localOut = path.join(work, "sensitive");
  const unlock = Buffer.alloc(32, 0x5a).toString("base64url");
  const local = await generateSensitiveCard({
    config: {
      accessMode: "acl+qr",
      cardId: "local-test-card",
      classification: "local-sensitive-locator-plus-unlock",
      locator: "https://github.com/example/private-candidate",
      unlock
    },
    outDir: localOut,
    projectRoot: repository
  });
  const [json, svg] = await Promise.all([
    readFile(local.jsonPath, "utf8"),
    readFile(local.svgPath, "utf8")
  ]);
  const payload = JSON.parse(json);
  assert.deepEqual(Object.keys(payload).sort(), ["locator", "schema", "unlock_fragment"]);
  assert.deepEqual(payload, {
    locator: "https://github.com/example/private-candidate",
    schema: "hive-hub-qr-join-card/1",
    unlock_fragment: unlock
  });
  assert.match(svg, /xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
  assert.ok(!resultA.files.some((filePath) => filePath.includes("sensitive")));
  const runner = path.join(repository, "skills/hive-hub/scripts/run.py");
  const decoded = spawnSync(
    process.env.PYTHON || "python3",
    ["-I", "-B", runner, "decode", "--card-stdin"],
    {
      cwd: repository,
      encoding: "utf8",
      input: json
    }
  );
  assert.equal(decoded.status, 0, decoded.stderr || decoded.stdout);
  const decodedResult = JSON.parse(decoded.stdout);
  assert.equal(decodedResult.card_source, "card-stdin");
  assert.equal(decodedResult.has_optional_factor, true);
  assert.doesNotMatch(decoded.stdout, new RegExp(unlock));

  await assert.rejects(
    generateSensitiveCard({
      config: {
        accessMode: "acl+qr",
        cardId: "must-fail",
        classification: "local-sensitive-locator-plus-unlock",
        locator: "https://github.com/example/private-candidate",
        unlock
      },
      outDir: path.join(repository, "hub/private-card"),
      projectRoot: repository
    }),
    /Sensitive cards may be written only/
  );
});

test("bare join URL guides the visitor without fetching or reporting verification failure", async () => {
  const joinScript = await readFile(path.join(buildA, "hub/join/join.js"), "utf8");
  const elements = new Map(
    ["status", "failure", "join-help"].map((id) => [id, { hidden: true, textContent: "" }])
  );
  let fetches = 0;
  vm.runInNewContext(joinScript, {
    document: { getElementById: (id) => elements.get(id) },
    fetch: () => { fetches += 1; throw new Error("unexpected fetch"); },
    window: {
      location: { hash: "", pathname: "/hub/join/", search: "" },
      history: { replaceState() {} }
    }
  });
  assert.equal(fetches, 0);
  assert.equal(elements.get("join-help").hidden, false);
  assert.equal(elements.get("failure").hidden, true);
  assert.match(elements.get("status").textContent, /No join card supplied/);
});

test("generated join script executes the real core camera-card path", async () => {
  const coreCard = resultA.cards[0].cameraAiCard;
  const cardBytes = await readFile(path.join(buildA, coreCard.path));
  const cardDocument = JSON.parse(cardBytes);
  const joinScript = await readFile(path.join(buildA, "hub/join/join.js"), "utf8");
  const elements = new Map(
    ["status", "failure", "machine-readable", "machine-section"].map((id) => [
      id,
      { hidden: id !== "failure", textContent: "" }
    ])
  );
  let finish;
  const completed = new Promise((resolve) => {
    finish = resolve;
  });
  const status = elements.get("status");
  Object.defineProperty(status, "textContent", {
    get() {
      return this.value || "";
    },
    set(value) {
      this.value = value;
      if (value === "Core camera-AI join card verified. Resolve its locator with the matching Hive Hub client." ||
          value === "Verification failed.") {
        finish(value);
      }
    }
  });
  const location = new URL(
    `https://kody-w.github.io/hive-hub/hub/join/${resultA.cards[0].cameraQrFragment}`
  );
  const context = {
    TextDecoder,
    TextEncoder,
    URL,
    URLSearchParams,
    Uint8Array,
    atob,
    btoa,
    console,
    crypto: webcrypto,
    document: {
      getElementById(id) {
        return elements.get(id);
      }
    },
    fetch: async (url) => {
      assert.equal(String(url), coreCard.url);
      return {
        ok: true,
        async arrayBuffer() {
          return cardBytes.buffer.slice(
            cardBytes.byteOffset,
            cardBytes.byteOffset + cardBytes.byteLength
          );
        }
      };
    },
    setTimeout,
    window: {
      atob,
      btoa,
      crypto: webcrypto,
      history: {
        replaceState() {}
      },
      location: {
        hash: location.hash,
        href: location.href,
        origin: location.origin,
        pathname: location.pathname,
        search: location.search
      }
    }
  };
  vm.runInNewContext(joinScript, context);
  const finalStatus = await Promise.race([
    completed,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error("core camera-card path timed out")), 2000)
    )
  ]);
  assert.equal(
    finalStatus,
    "Core camera-AI join card verified. Resolve its locator with the matching Hive Hub client.",
    elements.get("failure").textContent
  );
  const machine = JSON.parse(elements.get("machine-readable").textContent);
  assert.deepEqual(machine.card, cardDocument);
  assert.equal(machine.verification.coreContract, "verified");
});

test("organization join verifies the exact package and refuses a different seed", async () => {
  const publishedCards = await Promise.all(resultA.cards.map(async (card) => ({
    ...card,
    document: JSON.parse(await readFile(path.join(buildA, card.descriptor.path), "utf8"))
  })));
  const seedCards = publishedCards.filter((card) => card.document.seed);
  assert.equal(seedCards.length, 10);
  const selected = seedCards[0];
  const joinScript = await readFile(path.join(buildA, "hub/join/join.js"), "utf8");
  for (const tampered of [false, true]) {
    const document = structuredClone(selected.document);
    if (tampered) document.seed = seedCards[1].document.seed;
    const cardBytes = Buffer.from(canonicalJson(document));
    const envelope = {
      card: selected.descriptor.url,
      sha256: sha256Bytes(cardBytes),
      v: 1
    };
    const location = new URL("https://kody-w.github.io/hive-hub/hub/join/");
    location.hash = "#v1." + Buffer.from(JSON.stringify(envelope)).toString("base64url");
    const elements = new Map([
      "status", "failure", "machine-readable", "machine-section", "verified-title",
      "summary", "steps", "repository-link", "json-link", "llms-link", "verified"
    ].map((id) => [id, {
      hidden: true, textContent: "", children: [], append(item) { this.children.push(item); }
    }]));
    let finish;
    const completed = new Promise((resolve) => { finish = resolve; });
    Object.defineProperty(elements.get("status"), "textContent", {
      set(value) {
        this.value = value;
        if (value.startsWith("Verification complete.") || value === "Verification failed.") {
          finish(value);
        }
      },
      get() { return this.value || ""; }
    });
    let cleared = false;
    const context = {
      TextDecoder, TextEncoder, URL, URLSearchParams, Uint8Array, atob, btoa,
      document: {
        getElementById: (id) => elements.get(id),
        createElement: () => ({ textContent: "" })
      },
      fetch: async (url) => {
        assert.equal(cleared, true, "The locator must leave history before fetching");
        const parsed = new URL(url);
        assert.equal(parsed.origin, location.origin);
        assert.ok(parsed.pathname.startsWith("/hive-hub/"));
        const bytes = String(url) === selected.descriptor.url
          ? cardBytes
          : await readFile(path.join(buildA, parsed.pathname.slice("/hive-hub/".length)));
        return {
          ok: true,
          arrayBuffer: async () => bytes.buffer.slice(
            bytes.byteOffset, bytes.byteOffset + bytes.byteLength
          )
        };
      },
      window: {
        atob, btoa, crypto: webcrypto,
        history: { replaceState() { cleared = true; } },
        location
      }
    };
    vm.runInNewContext(joinScript, context);
    let timer;
    const finalStatus = await Promise.race([
      completed,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("seed join verification timed out")), 3000);
      })
    ]);
    clearTimeout(timer);
    if (tampered) {
      assert.equal(finalStatus, "Verification failed.");
      assert.match(elements.get("failure").textContent, /disagree/);
      assert.equal(elements.get("verified").hidden, true);
    } else {
      assert.match(finalStatus, /^Verification complete/);
      const result = JSON.parse(elements.get("machine-readable").textContent);
      assert.equal(result.seed.status, "seed-not-activated");
      assert.equal(result.seed.counts.teams >= 5, true);
      assert.equal(elements.get("repository-link").href, result.seed.archive.url);
      assert.equal(elements.get("repository-link").download, result.seed.slug + ".zip");
    }
  }
});
