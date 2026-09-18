import path from "node:path";
import { rm } from "node:fs/promises";

import {
  CHANT_PROTOCOL,
  CHANT_VOCABULARY_PROVENANCE,
  CHANT_VOCABULARY_SHA256,
  deriveChant,
  verifyChant
} from "./lib/chant.mjs";
import {
  base64url,
  canonicalJson,
  contentRef,
  isMain,
  OutputWriter,
  parseCliArgs,
  publicUrl,
  removePublicSurface,
  sha256Bytes
} from "./lib/canonical.mjs";
import { loadPublicInputs } from "./lib/public-inputs.mjs";
import { createQrSvg } from "./lib/qr.mjs";
import {
  renderHomeHtml,
  renderHubCss,
  renderJoinHtml,
  renderJoinJavaScript,
  renderLlmsText
} from "./lib/render.mjs";
import { createSchemas } from "./lib/schemas.mjs";

const REQUIRED_ENTRY_KINDS = new Set([
  "adapter",
  "conformance",
  "learning-bundle",
  "protocol",
  "receipt",
  "record"
]);
const OPTIONAL_ENTRY_KINDS = new Set([
  "core-card",
  "core-schema",
  "historical-object",
  "historical-receipt",
  "release",
  "source-archive",
  "skill-declaration"
]);

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function without(source, ...keys) {
  const result = { ...source };
  for (const key of keys) {
    delete result[key];
  }
  return result;
}

function assertEntryIdentity(entry) {
  const document = entry.document;
  const expected = {
    adapter: ["adapterId", "urn:hive-hub:adapter:"],
    conformance: ["conformanceId", "urn:hive-hub:conformance:"],
    "learning-bundle": ["bundleId", "urn:hive-hub:learning:"],
    protocol: ["protocolId", "urn:hive-hub:protocol:"],
    record: ["recordId", ""]
  }[entry.declaration.kind];
  if (!expected) {
    return;
  }
  const [field, prefix] = expected;
  assert(typeof document[field] === "string", `${entry.path} is missing ${field}`);
  if (prefix) {
    assert(document[field].startsWith(prefix), `${entry.path} has an invalid ${field}`);
  } else {
    assert(document[field] === entry.declaration.id, `${entry.path} id does not match manifest`);
  }
}

function assertNoSensitivePublicFields(value, location = "$") {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoSensitivePublicFields(item, `${location}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") {
    if (typeof value === "string" && /microsol/i.test(value)) {
      throw new Error(`Public input contains a prohibited private-network identifier at ${location}`);
    }
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (/^(password|privateKey|secret|token|unlock|unlockCommitment)$/i.test(key)) {
      throw new Error(`Public input contains sensitive field ${location}.${key}`);
    }
    if (/credential/i.test(key) && child !== false && child !== "existing-source-acl") {
      throw new Error(`Public input contains credential material at ${location}.${key}`);
    }
    assertNoSensitivePublicFields(child, `${location}.${key}`);
  }
}

function groupEntries(entries) {
  const grouped = new Map();
  for (const kind of [...REQUIRED_ENTRY_KINDS, ...OPTIONAL_ENTRY_KINDS]) {
    grouped.set(kind, []);
  }
  for (const entry of entries) {
    assertEntryIdentity(entry);
    assertNoSensitivePublicFields(entry.document);
    grouped.get(entry.declaration.kind).push(entry);
  }
  for (const kind of REQUIRED_ENTRY_KINDS) {
    assert(grouped.get(kind).length > 0, `Public manifest has no ${kind} entry`);
  }
  return grouped;
}

async function writeRawContentObject(writer, {
  apiPath,
  category,
  document,
  siteBaseUrl
}) {
  const bytes = Buffer.from(canonicalJson(document));
  const digest = sha256Bytes(bytes);
  const outputPath = `${apiPath}/${category}/sha256/${digest.slice(0, 2)}/${digest}.json`;
  await writer.write(outputPath, bytes);
  return {
    descriptor: descriptorFor(outputPath, digest, siteBaseUrl),
    digest,
    document
  };
}

function descriptorFor(pathValue, digest, siteBaseUrl) {
  return {
    path: pathValue,
    ref: contentRef(digest),
    url: publicUrl(siteBaseUrl, pathValue)
  };
}

function schemaUrl(siteBaseUrl, apiPath, name) {
  return publicUrl(siteBaseUrl, `${apiPath}/schemas/${name}.schema.json`);
}

function assertReference(objects, id, expectedKind, owner) {
  const value = objects.get(id);
  assert(value, `${owner} references unknown object ${id}`);
  assert(value.kind === expectedKind, `${owner} references ${id} as ${expectedKind}, got ${value.kind}`);
  return value;
}

function selectBucket(buckets, digest) {
  const firstByte = Number.parseInt(digest.slice(0, 2), 16);
  const bucket = buckets.find(
    (candidate) =>
      firstByte >= Number.parseInt(candidate.minimum, 16) &&
      firstByte <= Number.parseInt(candidate.maximum, 16)
  );
  assert(bucket, `No bucket covers SHA-256 prefix ${digest.slice(0, 2)}`);
  return bucket;
}

function validateProtocol(document) {
  assert(document.kind === "protocol-declaration", "Protocol input has the wrong kind");
  assert(
    typeof document.version === "string" && /^[0-9A-Za-z][0-9A-Za-z.+-]*$/.test(document.version),
    "Protocol declaration must name an exact version"
  );
  assert(document.semantics?.authority?.includes("locator only"), "Protocol must bound locator authority");
  assert(
    document.semantics?.activation?.includes("inert"),
    "Protocol must keep downloaded content inert"
  );
}

function validateLearningBundle(document) {
  assert(document.kind === "learning-bundle", "Learning bundle input has the wrong kind");
  assert(document.inertByDefault === true, "Learning bundle must be inert by default");
  assert(Array.isArray(document.steps) && document.steps.length >= 4, "Learning bundle is incomplete");
}

function validateConformance(document) {
  assert(document.kind === "conformance-contract", "Conformance input has the wrong kind");
  assert(
    Array.isArray(document.claimsNeverGranted) && document.claimsNeverGranted.length > 0,
    "Conformance contract must state claims it never grants"
  );
  assert(
    Array.isArray(document.requirements) && document.requirements.length >= 4,
    "Conformance contract is incomplete"
  );
}

function validateAdapter(document) {
  assert(document.kind === "adapter-declaration", "Adapter input has the wrong kind");
  assert(document.executable === false, "Published adapter declaration must be non-executable");
  assert(
    Array.isArray(document.semanticCompatibilityClaims) &&
      document.semanticCompatibilityClaims.length === 0,
    "Example adapter must not claim semantic compatibility"
  );
}

function validateRecord(document) {
  assert(document.kind === "dial-record", "Record input has the wrong kind");
  assert(document.visibility === "public", "Public build accepts only public Dial Records");
  assert(document.access?.mode === "acl-only", "Public Dial Records default to acl-only");
  assert(
    typeof document.dialId === "string" && /^dial:sha256:[a-f0-9]{64}$/.test(document.dialId),
    "Record needs a full canonical Dial Record ID"
  );
  assert(document.chantProtocolId === "hive-hub-chant-v1", "Record uses the wrong chant contract");
  assert(
    Array.isArray(document.aliases) &&
      document.aliases.length > 0 &&
      document.aliases.every((alias) => /^[a-z0-9][a-z0-9._-]*$/.test(alias)),
    "Record aliases must be explicit display/search strings"
  );
  assert(Array.isArray(document.chants) && document.chants.length === 1, "Record needs one derived chant locator");
  assert(
    document.chants.every((chant) => chant.role === "candidate-locator-only"),
    "Every chant must be candidate-locator-only"
  );
  verifyChant(document.dialId, document.chants[0].value);
  assert(
    !document.aliases.includes(document.chants[0].value),
    "A display/search alias cannot also occupy the chant field"
  );
  assert(
    Array.isArray(document.claims?.authority) && document.claims.authority.length === 0,
    "Example record must not claim authority"
  );
  assert(
    Array.isArray(document.claims?.semanticCompatibility) &&
      document.claims.semanticCompatibility.length === 0,
    "Example record must not claim semantic compatibility"
  );
  assert(
    /^[a-f0-9]{40}$/.test(document.locator?.revision),
    "Repository revision must be one exact lowercase Git commit"
  );
  const expectedRepository =
    `https://github.com/${document.locator.owner}/${document.locator.repository}`;
  assert(
    document.locator.repositoryUrl === expectedRepository,
    "Repository URL must exactly match owner and repository"
  );
  assert(
    document.locator.browseUrl ===
      `${expectedRepository}/tree/${document.locator.revision}`,
    "Browse URL must retain the exact commit"
  );
  assert(
    document.locator.archiveUrl ===
      `${expectedRepository}/archive/${document.locator.revision}.tar.gz`,
    "Archive URL must retain the exact commit"
  );
  assert(
    document.locator.rawBaseUrl ===
      `https://raw.githubusercontent.com/${document.locator.owner}/${document.locator.repository}/${document.locator.revision}`,
    "Raw URL must retain the exact commit"
  );
  assert(document.security?.credentialsIncluded === false, "Public record cannot contain credentials");
}

function validateRelease(document, manifest) {
  assert(document.kind === "hive-hub-release", "Release input has the wrong kind");
  assert(document.version === manifest.productVersion, "Release version does not match manifest");
  assert(document.core?.version === manifest.productVersion, "Core release version is inconsistent");
  assert(document.skill?.version === manifest.productVersion, "Skill release version is inconsistent");
  assert(document.adapters?.optional === true, "Adapter package must remain optional");
  assert(document.static?.publicInputsOnly === true, "Static release must be public-input-only");
  assert(document.chant?.protocol === CHANT_PROTOCOL, "Release chant protocol is inconsistent");
  assert(
    document.chant?.vocabularySha256 === CHANT_VOCABULARY_SHA256,
    "Release chant vocabulary hash is inconsistent"
  );
  assert(
    document.chant?.requiresRappIdentity === false &&
      document.chant?.requiresRappRuntime === false &&
      document.chant?.candidateLocatorOnly === true &&
      document.chant?.fullDialIdVerificationRequired === true,
    "Release chant authority or runtime boundary is invalid"
  );
  assert(
    document.publicSample?.repository === "kody-w/hive-hub" &&
      document.publicSample?.revision === "8e9ee55a7eb9fe4b4aaa084290e1916c0edcade9" &&
      document.publicSample?.dialId ===
        "dial:sha256:6b822d070281ee28b89c3c4209e5ba6e796a09ec5973da6e73324cee44127c32" &&
      document.publicSample?.chant === deriveChant(document.publicSample.dialId),
    "Release metadata does not bind the allowed public sample"
  );
}

function validateSkillDeclaration(document) {
  assert(document.schema === "hive-hub-declaration/1", "Skill declaration has the wrong schema");
  assert(/^dial:sha256:[a-f0-9]{64}$/.test(document.id), "Skill declaration id is invalid");
  assert(document.access?.visibility === "public", "Skill declaration must be public");
  assert(document.access?.mode === "acl-only", "Skill declaration must use acl-only");
  assert(document.join?.kind === "subscription", "Public skill declaration must remain inert");
  assert(document.extensions?.authority === false, "Skill declaration must not claim authority");
}

function validateCoreCard(document) {
  const keys = Object.keys(document).sort().join(",");
  assert(
    keys ===
      "adapter_plan,card_id,expected_protocol_fingerprint,expected_record_id,issued_at,kind,locator,principal,schema_version",
    "Core AI join card is not a closed contract"
  );
  assert(document.kind === "ai-join-card" && document.schema_version === 1, "Core card kind is invalid");
  assert(document.adapter_plan === null, "Public camera card cannot carry adapter effects");
  assert(
    document.expected_record_id === null && document.expected_protocol_fingerprint === null,
    "Public camera card cannot claim undeclared core identities"
  );
  const body = {
    kind: "ai-join-card-body",
    schema_version: 1,
    principal: document.principal,
    locator: document.locator,
    expected_record_id: null,
    expected_protocol_fingerprint: null,
    adapter_plan: null,
    issued_at: document.issued_at
  };
  const bodyDigest = sha256Bytes(Buffer.from(canonicalJson(body).trimEnd()));
  assert(
    document.card_id === `urn:hivehub:sha256:${bodyDigest}`,
    "Core AI join card id does not match its canonical body"
  );
}

async function writeContentObject(writer, {
  apiPath,
  category,
  document,
  schemaName,
  siteBaseUrl,
  bucket
}) {
  const withSchema = {
    $schema: schemaUrl(siteBaseUrl, apiPath, schemaName),
    ...document
  };
  const bytes = Buffer.from(canonicalJson(withSchema));
  const digest = sha256Bytes(bytes);
  const shard = bucket ?? digest.slice(0, 2);
  const outputPath = `${apiPath}/${category}/sha256/${shard}/${digest}.json`;
  await writer.write(outputPath, bytes);
  return {
    descriptor: descriptorFor(outputPath, digest, siteBaseUrl),
    digest,
    document: withSchema
  };
}

function contentObject(kind, id, stored) {
  return {
    ...stored,
    id,
    kind
  };
}

function sortedObject(entries) {
  return Object.fromEntries([...entries].sort(([left], [right]) => left.localeCompare(right)));
}

async function writeStableJson(writer, pathValue, document, siteBaseUrl) {
  const result = await writer.writeJson(pathValue, document);
  return {
    descriptor: descriptorFor(pathValue, result.digest, siteBaseUrl),
    document
  };
}

export async function buildStaticSurface({ manifestPath, outDir }) {
  if (!manifestPath || !outDir) {
    throw new Error("buildStaticSurface requires explicit manifestPath and outDir");
  }
  const loaded = await loadPublicInputs(manifestPath);
  const { manifest, audit } = loaded;
  const grouped = groupEntries(loaded.entries);
  const resolvedOut = path.resolve(outDir);
  const sourceRoot = path.resolve(loaded.manifestDirectory, manifest.sourceRoot);
  const relativeOut = path.relative(loaded.manifestDirectory, resolvedOut).split(path.sep).join("/");
  assert(
    resolvedOut !== sourceRoot && !resolvedOut.startsWith(`${sourceRoot}${path.sep}`),
    "Public output cannot be written inside public-src"
  );
  assert(
    relativeOut === "" ||
      relativeOut === "site" ||
      relativeOut.startsWith("site/") ||
      relativeOut === "tests/.work" ||
      relativeOut.startsWith("tests/.work/") ||
      relativeOut === ".hive-hub/build" ||
      relativeOut.startsWith(".hive-hub/build/"),
    "Public output must be the repository root or an approved ignored build directory"
  );

  if (relativeOut === "") {
    await removePublicSurface(resolvedOut);
  } else {
    await rm(resolvedOut, { force: true, recursive: true });
  }
  const writer = new OutputWriter(resolvedOut);
  const { apiPath, generatedAt, rawBaseUrl, siteBaseUrl } = manifest.build;
  const objects = new Map();
  const immutableObjects = [];
  const historicalReceipts = new Map();

  for (const entry of loaded.entries) {
    await writer.writeJson(`${apiPath}/source/${entry.path}`, entry.document);
  }

  for (const entry of grouped.get("historical-receipt")) {
    assert(entry.document.kind === "receipt", `${entry.path} is not a historical receipt`);
    assert(
      Number.isInteger(entry.document.sequence) && entry.document.sequence > 0,
      `${entry.path} has an invalid historical receipt sequence`
    );
    assert(
      !historicalReceipts.has(entry.document.sequence),
      `Duplicate historical receipt sequence ${entry.document.sequence}`
    );
    const outputPath =
      `${apiPath}/receipts/sha256/${entry.digest.slice(0, 2)}/${entry.digest}.json`;
    const stored = await writer.write(outputPath, entry.bytes);
    assert(stored.digest === entry.digest, `${entry.path} historical receipt hash changed`);
    const object = contentObject("receipt", entry.declaration.id, {
      descriptor: descriptorFor(outputPath, entry.digest, siteBaseUrl),
      digest: entry.digest,
      document: entry.document
    });
    historicalReceipts.set(entry.document.sequence, object);
    immutableObjects.push(object);
  }

  for (const entry of grouped.get("historical-object")) {
    let outputPath;
    if (entry.declaration.id.startsWith("historical-core-card-")) {
      assert(entry.document.kind === "ai-join-card", `${entry.path} is not a core card`);
      outputPath =
        `${apiPath}/cards/core/sha256/${entry.digest.slice(0, 2)}/${entry.digest}.json`;
    } else if (entry.document.kind === "ai-join-card") {
      outputPath = `${apiPath}/cards/sha256/${entry.digest.slice(0, 2)}/${entry.digest}.json`;
    } else if (entry.document.kind === "dial-record") {
      const bucket = selectBucket(manifest.buckets, entry.digest);
      outputPath = `${apiPath}/records/sha256/${bucket.id}/${entry.digest}.json`;
    } else if (entry.document.kind === "hive-hub-release") {
      outputPath = `${apiPath}/releases/sha256/${entry.digest.slice(0, 2)}/${entry.digest}.json`;
    } else if (entry.document.schema === "hive-hub-declaration/1") {
      outputPath = `${apiPath}/declarations/sha256/${entry.digest.slice(0, 2)}/${entry.digest}.json`;
    } else {
      throw new Error(`${entry.path} is not a supported historical object`);
    }
    const stored = await writer.write(outputPath, entry.bytes);
    assert(stored.digest === entry.digest, `${entry.path} historical object hash changed`);
    immutableObjects.push(
      contentObject("historical-object", entry.declaration.id, {
        descriptor: descriptorFor(outputPath, entry.digest, siteBaseUrl),
        digest: entry.digest,
        document: entry.document
      })
    );
  }

  const coreSchemaDescriptors = [];
  for (const entry of grouped.get("core-schema")) {
    assert(
      entry.document.$schema === "https://json-schema.org/draft/2020-12/schema",
      `${entry.path} is not a core JSON Schema`
    );
    const name = path.posix.basename(entry.path);
    const outputPath = `${apiPath}/core-schemas/${name}`;
    const stored = await writer.write(outputPath, entry.bytes);
    coreSchemaDescriptors.push({
      name,
      ...descriptorFor(outputPath, stored.digest, siteBaseUrl)
    });
  }
  coreSchemaDescriptors.sort((left, right) => left.name.localeCompare(right.name));
  const coreSchemasIndex = await writeStableJson(
    writer,
    `${apiPath}/core-schemas/index.json`,
    {
      kind: "core-schema-index",
      productVersion: manifest.productVersion,
      schemas: coreSchemaDescriptors
    },
    siteBaseUrl
  );

  assert(grouped.get("release").length === 1, "Public build requires one integrated release");
  const releaseEntry = grouped.get("release")[0];
  validateRelease(releaseEntry.document, manifest);
  const releaseStored = await writeRawContentObject(writer, {
    apiPath,
    category: "releases",
    document: releaseEntry.document,
    siteBaseUrl
  });
  const releaseObject = contentObject(
    "release",
    releaseEntry.declaration.id,
    releaseStored
  );
  immutableObjects.push(releaseObject);
  const releaseIndex = await writeStableJson(
    writer,
    `${apiPath}/release.json`,
    {
      current: releaseObject.descriptor,
      kind: "release-index",
      version: manifest.productVersion
    },
    siteBaseUrl
  );

  const skillDeclarations = new Map();
  for (const entry of grouped.get("skill-declaration")) {
    validateSkillDeclaration(entry.document);
    const stored = await writeRawContentObject(writer, {
      apiPath,
      category: "declarations",
      document: entry.document,
      siteBaseUrl
    });
    const object = contentObject(
      "skill-declaration",
      entry.declaration.id,
      stored
    );
    skillDeclarations.set(object.id, object);
    immutableObjects.push(object);
  }

  const coreCards = new Map();
  for (const entry of grouped.get("core-card")) {
    validateCoreCard(entry.document);
    const stored = await writeRawContentObject(writer, {
      apiPath,
      category: "cards/core",
      document: entry.document,
      siteBaseUrl
    });
    const object = contentObject("core-card", entry.declaration.id, stored);
    coreCards.set(object.id, object);
    immutableObjects.push(object);
  }

  const schemas = createSchemas(publicUrl(siteBaseUrl, `${apiPath}/schemas`));
  const schemaDescriptors = [];
  for (const [name, document] of Object.entries(schemas).sort(([left], [right]) =>
    left.localeCompare(right)
  )) {
    const schemaPath = `${apiPath}/schemas/${name}`;
    const stored = await writeStableJson(writer, schemaPath, document, siteBaseUrl);
    schemaDescriptors.push({
      name,
      ...stored.descriptor
    });
  }
  const schemasIndex = await writeStableJson(
    writer,
    `${apiPath}/schemas/index.json`,
    {
      kind: "schema-index",
      schemas: schemaDescriptors,
      version: "1.0.0"
    },
    siteBaseUrl
  );

  for (const entry of grouped.get("protocol")) {
    validateProtocol(entry.document);
    const stored = await writeContentObject(writer, {
      apiPath,
      category: "protocols",
      document: entry.document,
      schemaName: "protocol-declaration",
      siteBaseUrl
    });
    const object = contentObject("protocol", entry.declaration.id, stored);
    objects.set(object.id, object);
    immutableObjects.push(object);
  }

  for (const entry of grouped.get("learning-bundle")) {
    validateLearningBundle(entry.document);
    const protocol = assertReference(
      objects,
      entry.document.protocolId,
      "protocol",
      entry.declaration.id
    );
    const document = {
      ...without(entry.document, "protocolId"),
      protocol: protocol.descriptor,
      protocolFingerprint: protocol.descriptor.ref
    };
    const stored = await writeContentObject(writer, {
      apiPath,
      category: "learning-bundles",
      document,
      schemaName: "learning-bundle",
      siteBaseUrl
    });
    const object = contentObject("learning-bundle", entry.declaration.id, stored);
    objects.set(object.id, object);
    immutableObjects.push(object);
  }

  for (const entry of grouped.get("conformance")) {
    validateConformance(entry.document);
    const protocol = assertReference(
      objects,
      entry.document.protocolId,
      "protocol",
      entry.declaration.id
    );
    const document = {
      ...without(entry.document, "protocolId"),
      protocol: protocol.descriptor,
      protocolFingerprint: protocol.descriptor.ref
    };
    const stored = await writeContentObject(writer, {
      apiPath,
      category: "conformance",
      document,
      schemaName: "conformance",
      siteBaseUrl
    });
    const object = contentObject("conformance", entry.declaration.id, stored);
    objects.set(object.id, object);
    immutableObjects.push(object);
  }

  for (const entry of grouped.get("adapter")) {
    validateAdapter(entry.document);
    const protocol = assertReference(
      objects,
      entry.document.protocolId,
      "protocol",
      entry.declaration.id
    );
    const conformance = assertReference(
      objects,
      entry.document.conformanceId,
      "conformance",
      entry.declaration.id
    );
    const document = {
      ...without(entry.document, "protocolId", "conformanceId"),
      conformance: conformance.descriptor,
      protocol: protocol.descriptor,
      protocolFingerprint: protocol.descriptor.ref
    };
    const stored = await writeContentObject(writer, {
      apiPath,
      category: "adapters",
      document,
      schemaName: "adapter",
      siteBaseUrl
    });
    const object = contentObject("adapter", entry.declaration.id, stored);
    objects.set(object.id, object);
    immutableObjects.push(object);
  }

  const records = [];
  for (const entry of grouped.get("record")) {
    validateRecord(entry.document);
    const protocol = assertReference(
      objects,
      entry.document.protocolId,
      "protocol",
      entry.declaration.id
    );
    const learningBundle = assertReference(
      objects,
      entry.document.learningBundleId,
      "learning-bundle",
      entry.declaration.id
    );
    const conformance = assertReference(
      objects,
      entry.document.conformanceId,
      "conformance",
      entry.declaration.id
    );
    const adapter = assertReference(
      objects,
      entry.document.adapterId,
      "adapter",
      entry.declaration.id
    );
    const chantProtocol = assertReference(
      objects,
      entry.document.chantProtocolId,
      "protocol",
      entry.declaration.id
    );
    const document = {
      ...without(
        entry.document,
        "adapterId",
        "chantProtocolId",
        "conformanceId",
        "learningBundleId",
        "protocolId"
      ),
      adapter: adapter.descriptor,
      chantProtocol: chantProtocol.descriptor,
      chantProtocolFingerprint: chantProtocol.descriptor.ref,
      conformance: conformance.descriptor,
      learningBundle: learningBundle.descriptor,
      protocol: protocol.descriptor,
      protocolFingerprint: protocol.descriptor.ref
    };
    const preHash = sha256Bytes(
      Buffer.from(
        canonicalJson({
          $schema: schemaUrl(siteBaseUrl, apiPath, "dial-record"),
          ...document
        })
      )
    );
    const bucket = selectBucket(manifest.buckets, preHash);
    const stored = await writeContentObject(writer, {
      apiPath,
      bucket: bucket.id,
      category: "records",
      document,
      schemaName: "dial-record",
      siteBaseUrl
    });
    assert(stored.digest === preHash, "Record digest changed while selecting its bucket");
    const object = {
      ...contentObject("record", entry.declaration.id, stored),
      bucketId: bucket.id
    };
    objects.set(object.id, object);
    immutableObjects.push(object);
    records.push(object);
  }
  records.sort((left, right) => left.id.localeCompare(right.id));

  const cards = [];
  const cardIds = new Set();
  for (const declaration of manifest.cards) {
    assert(!cardIds.has(declaration.cardId), `Duplicate card id ${declaration.cardId}`);
    cardIds.add(declaration.cardId);
    assert(
      Object.keys(declaration).sort().join(",") ===
        "cardId,chant,coreCardId,recordId,skillDeclarationId,skillDialId,slug,title",
      `Public card ${declaration.cardId} contains unsupported fields`
    );
    const record = assertReference(objects, declaration.recordId, "record", declaration.cardId);
    const coreCard = coreCards.get(declaration.coreCardId);
    const skillDeclaration = skillDeclarations.get(declaration.skillDeclarationId);
    assert(coreCard, `Card ${declaration.cardId} references an unknown core card`);
    assert(
      skillDeclaration,
      `Card ${declaration.cardId} references an unknown skill declaration`
    );
    assert(
      coreCard.document.locator === declaration.skillDialId,
      `Card ${declaration.cardId} core locator does not match its locked skill Dial ID`
    );
    assert(
      record.document.dialId === declaration.skillDialId,
      `Card ${declaration.cardId} full Dial Record ID disagrees with its record`
    );
    assert(
      declaration.chant === deriveChant(declaration.skillDialId),
      `Card ${declaration.cardId} chant is not derived from its full Dial Record ID`
    );
    assert(
      record.document.aliases.includes(declaration.slug),
      `Card ${declaration.cardId} slug is not a declared display/search alias`
    );
    assert(
      record.document.chants.some((chant) => chant.value === declaration.chant),
      `Card ${declaration.cardId} chant is not declared by its record`
    );
    const cardDocument = {
      adapter: record.document.adapter,
      api: {
        hashes: publicUrl(siteBaseUrl, `${apiPath}/hashes.json`),
        index: publicUrl(siteBaseUrl, `${apiPath}/index.json`),
        llms: publicUrl(siteBaseUrl, "llms.txt"),
        offlineSeed: publicUrl(siteBaseUrl, `${apiPath}/offline-seed.json`)
      },
      aliases: record.document.aliases,
      cardId: declaration.cardId,
      cameraAiCard: coreCard.descriptor,
      chant: {
        protocol: CHANT_PROTOCOL,
        semantics: "candidate-array-locator-only",
        value: declaration.chant
      },
      classification: "public-locator-only",
      conformance: record.document.conformance,
      kind: "ai-join-card",
      dialId: declaration.skillDialId,
      fullDialIdVerificationRequired: true,
      learningBundle: record.document.learningBundle,
      protocol: record.document.protocol,
      record: record.descriptor,
      release: releaseObject.descriptor,
      skillDeclaration: skillDeclaration.descriptor,
      steps: [
        "Verify this card and every referenced object with SHA-256.",
        "Read the exact protocol declaration, learning bundle, conformance contract, and adapter.",
        "Treat the chant as one candidate locator among possible candidates, never unique authority.",
        "Use the source repository's existing access controls and exact pinned commit.",
        "Keep retrieved code and instructions inert until separately approved and verified."
      ],
      title: declaration.title,
      version: "1.0.0"
    };
    const stored = await writeContentObject(writer, {
      apiPath,
      category: "cards",
      document: cardDocument,
      schemaName: "card",
      siteBaseUrl
    });
    const envelope = {
      card: stored.descriptor.url,
      sha256: stored.digest,
      v: 1
    };
    assert(
      Object.keys(envelope).sort().join(",") === "card,sha256,v",
      "QR envelope exceeded locator-only fields"
    );
    const qrFragment = `#v1.${base64url(canonicalJson(envelope).trimEnd())}`;
    const qrUrl = `${siteBaseUrl.replace(/\/+$/, "")}/hub/join/${qrFragment}`;
    const qrSvg = createQrSvg(qrUrl, "M");
    const qrPath = `${apiPath}/cards/qr/${declaration.slug}.svg`;
    const qrResult = await writer.write(qrPath, qrSvg);
    const cameraEnvelope = {
      card: coreCard.descriptor.url,
      sha256: coreCard.digest,
      v: 1
    };
    const cameraQrFragment = `#v1.${base64url(canonicalJson(cameraEnvelope).trimEnd())}`;
    const cameraQrUrl = `${siteBaseUrl.replace(/\/+$/, "")}/hub/join/${cameraQrFragment}`;
    const cameraQrPath = `${apiPath}/cards/qr/${declaration.slug}-camera-ai.svg`;
    const cameraQrResult = await writer.write(
      cameraQrPath,
      createQrSvg(cameraQrUrl, "M")
    );
    const object = {
      ...contentObject("card", declaration.cardId, stored),
      qr: {
        path: qrPath,
        sha256: qrResult.digest,
        url: publicUrl(siteBaseUrl, qrPath)
      },
      cameraAiCard: coreCard,
      cameraQr: {
        path: cameraQrPath,
        sha256: cameraQrResult.digest,
        url: publicUrl(siteBaseUrl, cameraQrPath)
      },
      cameraQrFragment,
      cameraQrUrl,
      qrFragment,
      qrUrl,
      record
    };
    immutableObjects.push(object);
    cards.push(object);
  }
  cards.sort((left, right) => left.id.localeCompare(right.id));

  const receipts = [];
  let previousReceipt = null;
  const receiptEntries = [...grouped.get("receipt")].sort(
    (left, right) => left.document.sequence - right.document.sequence
  );
  for (const entry of receiptEntries) {
    assert(entry.document.kind === "receipt-source", `${entry.path} is not a receipt source`);
    assert(
      entry.document.sequence === receipts.length + 1,
      `Receipt sequence must be contiguous at ${entry.path}`
    );
    assert(Number.isFinite(Date.parse(entry.document.occurredAt)), `${entry.path} has invalid time`);
    const historical = historicalReceipts.get(entry.document.sequence);
    if (historical) {
      const historicalSource = without(
        historical.document,
        "$schema",
        "card",
        "kind",
        "previous",
        "subject"
      );
      const currentSource = without(entry.document, "kind", "recordId");
      assert(
        canonicalJson(historicalSource) === canonicalJson(currentSource),
        `${entry.path} no longer matches its immutable historical receipt`
      );
      assert(
        canonicalJson(historical.document.previous) ===
          canonicalJson(previousReceipt?.descriptor ?? null),
        `${entry.path} historical predecessor changed`
      );
      receipts.push(historical);
      previousReceipt = historical;
      continue;
    }
    const record = assertReference(
      objects,
      entry.document.recordId,
      "record",
      entry.declaration.id
    );
    const relatedCard = cards.find((card) => card.record.id === record.id);
    const receiptDocument = {
      ...without(entry.document, "kind", "recordId"),
      card: relatedCard?.descriptor ?? null,
      kind: "receipt",
      previous: previousReceipt?.descriptor ?? null,
      subject: record.descriptor
    };
    const stored = await writeContentObject(writer, {
      apiPath,
      category: "receipts",
      document: receiptDocument,
      schemaName: "receipt",
      siteBaseUrl
    });
    const object = contentObject("receipt", entry.declaration.id, stored);
    receipts.push(object);
    immutableObjects.push(object);
    previousReceipt = object;
  }
  for (const sequence of historicalReceipts.keys()) {
    assert(
      receipts.some((receipt) => receipt.document.sequence === sequence),
      `Historical receipt sequence ${sequence} is not represented by the source ledger`
    );
  }

  const bucketIndexes = [];
  for (const bucket of manifest.buckets) {
    const bucketRecords = records
      .filter((record) => record.bucketId === bucket.id)
      .map((record) => record.descriptor);
    const bucketPath = `${apiPath}/buckets/${bucket.id}/index.json`;
    const stored = await writeStableJson(
      writer,
      bucketPath,
      {
        $schema: schemaUrl(siteBaseUrl, apiPath, "bucket-index"),
        algorithm: "sha256",
        bucketId: bucket.id,
        kind: "bucket-index",
        range: {
          maximum: bucket.maximum,
          minimum: bucket.minimum
        },
        records: bucketRecords
      },
      siteBaseUrl
    );
    bucketIndexes.push({
      bucketId: bucket.id,
      count: bucketRecords.length,
      index: stored.descriptor,
      range: {
        maximum: bucket.maximum,
        minimum: bucket.minimum
      }
    });
  }

  const bucketsIndex = await writeStableJson(
    writer,
    `${apiPath}/buckets/index.json`,
    {
      algorithm: "sha256",
      buckets: bucketIndexes,
      kind: "bucket-directory",
      routing: "Select exactly one bucket from the first byte of the record SHA-256 digest.",
      version: "1.0.0"
    },
    siteBaseUrl
  );

  const chantEntries = new Map();
  const aliasEntries = new Map();
  for (const record of records) {
    for (const chant of record.document.chants) {
      const candidates = chantEntries.get(chant.value) ?? [];
      candidates.push(record.descriptor);
      chantEntries.set(chant.value, candidates);
    }
    for (const alias of record.document.aliases) {
      const candidates = aliasEntries.get(alias) ?? [];
      candidates.push(record.descriptor);
      aliasEntries.set(alias, candidates);
    }
  }
  const chants = sortedObject(
    [...chantEntries].map(([chant, candidates]) => [
      chant,
      candidates.sort((left, right) => left.ref.localeCompare(right.ref))
    ])
  );
  const aliases = sortedObject(
    [...aliasEntries].map(([alias, candidates]) => [
      alias,
      candidates.sort((left, right) => left.ref.localeCompare(right.ref))
    ])
  );
  const dialbook = await writeStableJson(
    writer,
    `${apiPath}/dialbook.json`,
    {
      $schema: schemaUrl(siteBaseUrl, apiPath, "dialbook"),
      aliases,
      candidateSemantics: "Every chant maps to an array; no candidate is unique authority.",
      chant: {
        protocol: CHANT_PROTOCOL,
        vocabularyProvenance: CHANT_VOCABULARY_PROVENANCE,
        vocabularySha256: CHANT_VOCABULARY_SHA256,
        addressBits: 49,
        fullDialIdVerificationRequired: true
      },
      chants,
      generatedAt,
      kind: "public-dialbook",
      records: records.map((record) => record.descriptor),
      version: "1.0.0"
    },
    siteBaseUrl
  );

  const cardsIndex = await writeStableJson(
    writer,
    `${apiPath}/cards/index.json`,
    {
      cards: cards.map((card) => ({
        card: card.descriptor,
        cameraAiCard: card.cameraAiCard.descriptor,
        cameraQr: card.cameraQr,
        classification: "public-locator-only",
        qr: card.qr,
        record: card.record.descriptor
      })),
      kind: "card-index",
      version: "1.0.0"
    },
    siteBaseUrl
  );

  const receiptsIndex = await writeStableJson(
    writer,
    `${apiPath}/receipts/index.json`,
    {
      appendOnly: true,
      head: previousReceipt?.descriptor ?? null,
      kind: "receipt-index",
      ledger: "public-dialbook",
      receipts: receipts.map((receipt) => receipt.descriptor),
      version: "1.0.0"
    },
    siteBaseUrl
  );

  const federationMembers = [
    {
      bucketDirectory: bucketsIndex.descriptor,
      dialbook: dialbook.descriptor,
      hubId: "local-static-hub",
      relationship: "self"
    },
    ...manifest.federation.members.map((member) => ({
      hubId: member.hubId,
      indexUrl: member.indexUrl,
      relationship: "candidate-peer"
    }))
  ];
  const federationIndex = await writeStableJson(
    writer,
    `${apiPath}/federation/index.json`,
    {
      $schema: schemaUrl(siteBaseUrl, apiPath, "federation-index"),
      candidateSemantics: "union-without-authority",
      kind: "federation-index",
      members: federationMembers,
      version: "1.0.0"
    },
    siteBaseUrl
  );

  const federationRoutes = sortedObject(
    bucketIndexes.map((bucket) => [
      bucket.bucketId,
      [
        {
          hubId: "local-static-hub",
          index: bucket.index
        }
      ]
    ])
  );
  const federationBuckets = await writeStableJson(
    writer,
    `${apiPath}/federation/buckets.json`,
    {
      candidateSemantics: "Each route is an array of candidate bucket indexes.",
      kind: "federation-bucket-routes",
      routes: federationRoutes,
      version: "1.0.0"
    },
    siteBaseUrl
  );

  const status = await writeStableJson(
    writer,
    `${apiPath}/status.json`,
    {
      $schema: schemaUrl(siteBaseUrl, apiPath, "status"),
      counts: {
        adapters: grouped.get("adapter").length,
        buckets: bucketIndexes.length,
        cards: cards.length,
        coreCards: coreCards.size,
        coreSchemas: coreSchemaDescriptors.length,
        records: records.length,
        receipts: receipts.length
      },
      freshness: "The timestamp is a deterministic manifest value, not a live probe.",
      generatedAt,
      kind: "status",
      mode: "static-snapshot",
      status: "operational"
    },
    siteBaseUrl
  );

  const offlineObjects = sortedObject(
    immutableObjects.map((object) => [object.descriptor.ref, object.document])
  );
  const offlineRoutes = sortedObject(
    immutableObjects.map((object) => [object.descriptor.ref, object.descriptor.path])
  );
  const offlineSeed = await writeStableJson(
    writer,
    `${apiPath}/offline-seed.json`,
    {
      $schema: schemaUrl(siteBaseUrl, apiPath, "offline-seed"),
      discovery: {
        bucketDirectory: bucketsIndex.document,
        dialbook: dialbook.document
      },
      generatedAt,
      kind: "offline-seed",
      objects: offlineObjects,
      routes: offlineRoutes,
      verification: "Canonical UTF-8 JSON files end with LF and use SHA-256 content references.",
      version: "1.0.0"
    },
    siteBaseUrl
  );

  const joinAiDocument = {
    apiIndex: publicUrl(siteBaseUrl, `${apiPath}/index.json`),
    cameraAiCard: cards[0].cameraAiCard.descriptor,
    coreSchemas: coreSchemasIndex.descriptor,
    interpretation: [
      "Decode #v1.<base64url JSON> locally and replace browser history before network access.",
      "Accept envelope keys card, sha256, and v only.",
      "Fetch only same-origin static JSON and verify every sha256 content reference.",
      "Treat hive-hub-chant/1 and federation routes as candidate arrays; verify the complete Dial Record ID.",
      "Keep display/search aliases separate from chants.",
      "Read llms.txt and all declarations before acting; keep retrieved content inert."
    ],
    kind: "ai-join-instructions",
    llms: publicUrl(siteBaseUrl, "llms.txt"),
    release: releaseObject.descriptor,
    runtimeDependencies: [],
    version: manifest.productVersion
  };
  const joinAi = await writeStableJson(
    writer,
    "hub/join/ai.json",
    joinAiDocument,
    siteBaseUrl
  );

  const indexPath = `${apiPath}/index.json`;
  const indexDocument = {
    $schema: schemaUrl(siteBaseUrl, apiPath, "index"),
    apiVersion: "1.0.0",
    documents: {
      bucketDirectory: bucketsIndex.descriptor,
      cards: cardsIndex.descriptor,
      dialbook: dialbook.descriptor,
      federation: federationIndex.descriptor,
      federationBuckets: federationBuckets.descriptor,
      hashes: {
        path: `${apiPath}/hashes.json`,
        url: publicUrl(siteBaseUrl, `${apiPath}/hashes.json`)
      },
      offlineSeed: offlineSeed.descriptor,
      coreSchemas: coreSchemasIndex.descriptor,
      release: releaseIndex.descriptor,
      receipts: receiptsIndex.descriptor,
      schemas: schemasIndex.descriptor,
      status: status.descriptor
    },
    generatedAt,
    kind: "hive-hub-index",
    productVersion: manifest.productVersion,
    objectStores: {
      adapters: {
        addressing: "sha256",
        pathPattern: `${apiPath}/adapters/sha256/{first-byte}/{digest}.json`
      },
      cards: {
        addressing: "sha256",
        pathPattern: `${apiPath}/cards/sha256/{first-byte}/{digest}.json`
      },
      coreCards: {
        addressing: "sha256",
        pathPattern: `${apiPath}/cards/core/sha256/{first-byte}/{digest}.json`
      },
      conformance: {
        addressing: "sha256",
        pathPattern: `${apiPath}/conformance/sha256/{first-byte}/{digest}.json`
      },
      learningBundles: {
        addressing: "sha256",
        pathPattern: `${apiPath}/learning-bundles/sha256/{first-byte}/{digest}.json`
      },
      skillDeclarations: {
        addressing: "sha256",
        pathPattern: `${apiPath}/declarations/sha256/{first-byte}/{digest}.json`
      },
      protocols: {
        addressing: "sha256",
        pathPattern: `${apiPath}/protocols/sha256/{first-byte}/{digest}.json`
      },
      receipts: {
        addressing: "sha256",
        pathPattern: `${apiPath}/receipts/sha256/{first-byte}/{digest}.json`
      },
      records: {
        addressing: "sha256",
        pathPattern: `${apiPath}/records/sha256/{bucket-id}/{digest}.json`,
        sharding: "first-byte bucket directory"
      }
    },
    semantics: {
      activation: "inert-until-approved-and-verified",
      authority: "locators-never-authority",
      chants: "candidate-arrays",
      compatibility: "only-when-declared-adapter-and-conformance-prove-it"
    },
    transports: {
      pagesBaseUrl: siteBaseUrl,
      rawBaseUrl
    }
  };
  const apiIndex = await writeStableJson(writer, indexPath, indexDocument, siteBaseUrl);

  await writer.writeJson(".well-known/hive-hub.json", {
    apiVersion: "1.0.0",
    coreSchemas: coreSchemasIndex.descriptor,
    join: publicUrl(siteBaseUrl, "hub/join/"),
    kind: "hive-hub-well-known",
    llms: publicUrl(siteBaseUrl, "llms.txt"),
    pagesIndex: apiIndex.descriptor,
    release: releaseObject.descriptor,
    rawIndex: publicUrl(rawBaseUrl, indexPath)
  });

  const llmsText = renderLlmsText({
    apiIndexUrl: apiIndex.descriptor.url,
    dialbookUrl: dialbook.descriptor.url,
    exampleRecord: records[0].descriptor,
    cameraAiCard: cards[0].cameraAiCard.descriptor,
    joinAiUrl: joinAi.descriptor.url,
    release: releaseObject.descriptor,
    rawIndexUrl: publicUrl(rawBaseUrl, indexPath)
  });
  await writer.write("llms.txt", llmsText);
  await writer.write("hub/assets/hub.css", renderHubCss());
  await writer.write("hub/join/index.html", renderJoinHtml());
  await writer.write("hub/join/join.js", renderJoinJavaScript());
  await writer.write(
    "hub/index.html",
    renderHomeHtml({
      card: {
        ...cards[0].document,
        qrFragment: cards[0].qrFragment
      },
      generatedAt,
      qrPath: cards[0].qr.path,
      record: cards[0].record.document
    })
  );
  await writer.write(".nojekyll", "");

  const hashedFiles = sortedObject(
    [...writer.files]
      .map(([filePath, bytes]) => [
        filePath,
        {
          bytes: bytes.length,
          sha256: sha256Bytes(bytes)
        }
      ])
      .filter(([filePath]) => filePath !== `${apiPath}/hashes.json`)
  );
  const hashesDocument = {
    $schema: schemaUrl(siteBaseUrl, apiPath, "hashes"),
    algorithm: "sha256",
    build: {
      generatedAt,
      inspectedInputCount: audit.inspectedInputCount,
      inspectedInputs: audit.inspectedInputs,
      manifestCanonicalSha256: audit.manifestCanonicalSha256,
      manifestFileSha256: audit.manifestFileSha256,
      policy: audit.policy,
      privateBooksInspected: 0,
      sourceRoot: audit.sourceRoot,
      toolchain: {
        builder: "hive-hub-static-builder/1.0.0",
        canonicalJson: "sorted-object-keys-utf8-lf/1",
        qr: "qrcode-generator@1.4.4"
      }
    },
    files: hashedFiles,
    kind: "hash-manifest",
    selfHash: "omitted-to-avoid-recursion",
    version: "1.0.0"
  };
  await writer.writeJson(`${apiPath}/hashes.json`, hashesDocument);

  return {
    apiIndex: apiIndex.descriptor,
    audit,
    cards: cards.map((card) => ({
      cardId: card.id,
      descriptor: card.descriptor,
      envelope: {
        card: card.descriptor.url,
        sha256: card.digest,
        v: 1
      },
      cameraAiCard: card.cameraAiCard.descriptor,
      cameraEnvelope: {
        card: card.cameraAiCard.descriptor.url,
        sha256: card.cameraAiCard.digest,
        v: 1
      },
      cameraQrFragment: card.cameraQrFragment,
      cameraQrPath: card.cameraQr.path,
      qrFragment: card.qrFragment,
      qrPath: card.qr.path,
      qrUrl: card.qrUrl
    })),
    files: [...writer.files.keys()].sort(),
    hashesDocument,
    records: records.map((record) => ({
      descriptor: record.descriptor,
      document: record.document
    }))
  };
}

async function main() {
  const args = parseCliArgs(process.argv.slice(2));
  if (!args.manifest || !args.out) {
    throw new Error("Usage: node scripts/build.mjs --manifest public-manifest.json --out <directory>");
  }
  const result = await buildStaticSurface({
    manifestPath: args.manifest,
    outDir: args.out
  });
  process.stdout.write(
    `Built ${result.files.length} public files from ${result.audit.inspectedInputCount} explicit inputs (${result.audit.policy}).\n`
  );
}

if (isMain(import.meta.url)) {
  main().catch((error) => {
    process.stderr.write(`${error.stack ?? error.message}\n`);
    process.exitCode = 1;
  });
}
