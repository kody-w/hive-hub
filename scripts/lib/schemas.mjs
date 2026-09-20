import {
  CHANT_PROTOCOL,
  CHANT_VOCABULARY_SHA256,
  CHANT_WORDS
} from "./chant.mjs";

function schema(id, title, required, properties, extra = {}) {
  return {
    $id: id,
    $schema: "https://json-schema.org/draft/2020-12/schema",
    additionalProperties: true,
    properties,
    required,
    title,
    type: "object",
    ...extra
  };
}

const nonEmptyString = { minLength: 1, type: "string" };
const sha256Ref = { pattern: "^sha256:[a-f0-9]{64}$", type: "string" };
const httpsUrl = { format: "uri", pattern: "^https://", type: "string" };
const pathValue = { pattern: "^(?!/)(?!.*\\.\\.).+$", type: "string" };
const dialId = { pattern: "^dial:sha256:[a-f0-9]{64}$", type: "string" };
const alias = { pattern: "^[a-z0-9][a-z0-9._-]*$", type: "string" };
const chant = {
  pattern: `^(?:${CHANT_WORDS.join("|")})(?:-(?:${CHANT_WORDS.join("|")})){6}$`,
  type: "string"
};

export function createSchemas(schemaBaseUrl) {
  const base = schemaBaseUrl.replace(/\/+$/, "");
  const descriptor = {
    additionalProperties: false,
    properties: {
      path: pathValue,
      ref: sha256Ref,
      url: httpsUrl
    },
    required: ["path", "ref", "url"],
    type: "object"
  };

  return {
    "adapter.schema.json": schema(
      `${base}/adapter.schema.json`,
      "Hive Hub adapter declaration",
      [
        "$schema",
        "adapterId",
        "conformance",
        "executable",
        "kind",
        "protocol",
        "scope",
        "semanticCompatibilityClaims",
        "version"
      ],
      {
        $schema: httpsUrl,
        adapterId: nonEmptyString,
        conformance: descriptor,
        executable: { const: false },
        kind: { const: "adapter-declaration" },
        protocol: descriptor,
        scope: nonEmptyString,
        semanticCompatibilityClaims: { items: {}, type: "array" },
        version: nonEmptyString
      }
    ),
    "bucket-index.schema.json": schema(
      `${base}/bucket-index.schema.json`,
      "Hive Hub content-addressed bucket index",
      ["$schema", "algorithm", "bucketId", "kind", "records", "range"],
      {
        $schema: httpsUrl,
        algorithm: { const: "sha256" },
        bucketId: nonEmptyString,
        kind: { const: "bucket-index" },
        range: {
          properties: {
            maximum: { pattern: "^[a-f0-9]{2}$", type: "string" },
            minimum: { pattern: "^[a-f0-9]{2}$", type: "string" }
          },
          required: ["minimum", "maximum"],
          type: "object"
        },
        records: { items: descriptor, type: "array" }
      }
    ),
    "card.schema.json": schema(
      `${base}/card.schema.json`,
      "Hive Hub public locator-only AI join card",
      ["$schema", "api", "cardId", "classification", "kind", "record", "steps", "version"],
      {
        $schema: httpsUrl,
        aliases: { items: alias, minItems: 1, type: "array" },
        api: { type: "object" },
        cardId: nonEmptyString,
        cameraAiCard: descriptor,
        chant: {
          properties: {
            protocol: { const: CHANT_PROTOCOL },
            semantics: { const: "candidate-array-locator-only" },
            value: chant
          },
          required: ["protocol", "semantics", "value"],
          type: "object"
        },
        classification: { const: "public-locator-only" },
        dialId,
        legacySkillCard: descriptor,
        legacySkillDialId: dialId,
        fullDialIdVerificationRequired: { const: true },
        kind: { const: "ai-join-card" },
        record: descriptor,
        steps: { items: nonEmptyString, minItems: 1, type: "array" },
        version: { const: "1.0.0" }
      }
    ),
    "conformance.schema.json": schema(
      `${base}/conformance.schema.json`,
      "Hive Hub conformance contract",
      [
        "$schema",
        "claimsGrantedOnPass",
        "claimsNeverGranted",
        "conformanceId",
        "kind",
        "protocol",
        "requirements",
        "version"
      ],
      {
        $schema: httpsUrl,
        claimsGrantedOnPass: { items: nonEmptyString, type: "array" },
        claimsNeverGranted: { items: nonEmptyString, type: "array" },
        conformanceId: nonEmptyString,
        kind: { const: "conformance-contract" },
        protocol: descriptor,
        requirements: { items: { type: "object" }, minItems: 1, type: "array" },
        version: nonEmptyString
      }
    ),
    "dial-record.schema.json": schema(
      `${base}/dial-record.schema.json`,
      "Hive Hub public Dial Record",
      [
        "$schema",
        "access",
        "adapter",
        "chants",
        "claims",
        "conformance",
        "coreRecord",
        "coreContracts",
        "dialId",
        "kind",
        "learningBundle",
        "locator",
        "protocol",
        "recordId",
        "visibility"
      ],
      {
        $schema: httpsUrl,
        access: { type: "object" },
        adapter: descriptor,
        aliases: { items: alias, minItems: 1, type: "array" },
        chantProtocol: descriptor,
        chantProtocolFingerprint: sha256Ref,
        chants: {
          items: {
            properties: {
              role: { const: "candidate-locator-only" },
              value: nonEmptyString
            },
            required: ["role", "value"],
            type: "object"
          },
          minItems: 1,
          type: "array"
        },
        claims: {
          properties: {
            authority: { maxItems: 0, type: "array" },
            semanticCompatibility: { maxItems: 0, type: "array" }
          },
          required: ["authority", "semanticCompatibility"],
          type: "object"
        },
        conformance: descriptor,
        dialId,
        coreRecord: { $ref: `${base}/../core-schemas/dial-record.schema.json` },
        coreContracts: {
          additionalProperties: false,
          properties: {
            protocol: { $ref: `${base}/../core-schemas/protocol-declaration.schema.json` },
            learningBundle: { $ref: `${base}/../core-schemas/learning-bundle.schema.json` },
            adapter: { $ref: `${base}/../core-schemas/adapter-registration.schema.json` }
          },
          required: ["protocol", "learningBundle", "adapter"],
          type: "object"
        },
        kind: { const: "dial-record" },
        learningBundle: descriptor,
        locator: { type: "object" },
        protocol: descriptor,
        recordId: nonEmptyString,
        visibility: { const: "public" }
      }
    ),
    "dial-snapshot.schema.json": schema(
      `${base}/dial-snapshot.schema.json`,
      "Bounded single-fetch public dial snapshot",
      ["kind", "schema_version", "records"],
      {
        kind: { const: "published-dial-snapshot" },
        schema_version: { const: 1 },
        records: {
          type: "array",
          maxItems: 256,
          items: {
            additionalProperties: false,
            type: "object",
            required: ["ref", "record"],
            properties: {
              ref: sha256Ref,
              record: { $ref: `${base}/dial-record.schema.json` }
            }
          }
        }
      },
      { additionalProperties: false }
    ),
    "dialbook.schema.json": schema(
      `${base}/dialbook.schema.json`,
      "Hive Hub public dialbook",
      ["$schema", "chants", "kind", "records"],
      {
        $schema: httpsUrl,
        aliases: {
          additionalProperties: {
            items: descriptor,
            minItems: 1,
            type: "array"
          },
          type: "object"
        },
        candidateSemantics: {
          const: "Every chant maps to an array; no candidate is unique authority."
        },
        chant: {
          properties: {
            addressBits: { const: 49 },
            fullDialIdVerificationRequired: { const: true },
            protocol: { const: CHANT_PROTOCOL },
            vocabularyProvenance: nonEmptyString,
            vocabularySha256: { const: CHANT_VOCABULARY_SHA256 }
          },
          required: [
            "protocol",
            "vocabularyProvenance",
            "vocabularySha256",
            "addressBits",
            "fullDialIdVerificationRequired"
          ],
          type: "object"
        },
        chants: {
          additionalProperties: {
            items: descriptor,
            minItems: 1,
            type: "array"
          },
          type: "object"
        },
        generatedAt: nonEmptyString,
        kind: { const: "public-dialbook" },
        records: { items: descriptor, type: "array" },
        version: { const: "1.0.0" }
      }
    ),
    "federation-index.schema.json": schema(
      `${base}/federation-index.schema.json`,
      "Hive Hub federation index",
      ["$schema", "candidateSemantics", "kind", "members"],
      {
        $schema: httpsUrl,
        candidateSemantics: { const: "union-without-authority" },
        kind: { const: "federation-index" },
        members: { items: { type: "object" }, minItems: 1, type: "array" }
      }
    ),
    "hashes.schema.json": schema(
      `${base}/hashes.schema.json`,
      "Hive Hub public build hashes",
      ["$schema", "algorithm", "build", "files", "kind"],
      {
        $schema: httpsUrl,
        algorithm: { const: "sha256" },
        build: { type: "object" },
        files: {
          additionalProperties: {
            properties: {
              bytes: { minimum: 0, type: "integer" },
              sha256: { pattern: "^[a-f0-9]{64}$", type: "string" }
            },
            required: ["bytes", "sha256"],
            type: "object"
          },
          type: "object"
        },
        kind: { const: "hash-manifest" }
      }
    ),
    "index.schema.json": schema(
      `${base}/index.schema.json`,
      "Hive Hub static API index",
      ["$schema", "apiVersion", "documents", "kind", "objectStores", "semantics"],
      {
        $schema: httpsUrl,
        apiVersion: { const: "1.0.0" },
        documents: { type: "object" },
        kind: { const: "hive-hub-index" },
        objectStores: { type: "object" },
        semantics: { type: "object" }
      }
    ),
    "learning-bundle.schema.json": schema(
      `${base}/learning-bundle.schema.json`,
      "Hive Hub learning bundle",
      ["$schema", "bundleId", "inertByDefault", "kind", "protocol", "steps", "version"],
      {
        $schema: httpsUrl,
        bundleId: nonEmptyString,
        inertByDefault: { const: true },
        kind: { const: "learning-bundle" },
        protocol: descriptor,
        steps: { items: { type: "object" }, minItems: 1, type: "array" },
        version: nonEmptyString
      }
    ),
    "offline-seed.schema.json": schema(
      `${base}/offline-seed.schema.json`,
      "Hive Hub offline seed",
      ["$schema", "discovery", "kind", "objects", "routes", "version"],
      {
        $schema: httpsUrl,
        discovery: { type: "object" },
        kind: { const: "offline-seed" },
        objects: { type: "object" },
        routes: { type: "object" },
        version: { const: "1.0.0" }
      }
    ),
    "protocol-declaration.schema.json": schema(
      `${base}/protocol-declaration.schema.json`,
      "Hive Hub protocol declaration",
      ["$schema", "kind", "mediaTypes", "protocolId", "semantics", "transport", "version"],
      {
        $schema: httpsUrl,
        kind: { const: "protocol-declaration" },
        mediaTypes: { items: nonEmptyString, minItems: 1, type: "array" },
        protocolId: nonEmptyString,
        semantics: { type: "object" },
        transport: { type: "object" },
        version: nonEmptyString
      }
    ),
    "public-manifest.schema.json": schema(
      `${base}/public-manifest.schema.json`,
      "Hive Hub explicit public-only build manifest",
      [
        "build",
        "buckets",
        "cards",
        "classification",
        "entries",
        "federation",
        "manifestVersion",
        "productVersion",
        "sourceRoot"
      ],
      {
        build: { type: "object" },
        buckets: { items: { type: "object" }, minItems: 2, type: "array" },
        cards: { items: { type: "object" }, minItems: 1, type: "array" },
        classification: { const: "public-only" },
        entries: {
          items: {
            properties: {
              classification: { const: "public" },
              id: nonEmptyString,
              kind: nonEmptyString,
              path: pathValue,
              sha256: { pattern: "^[a-f0-9]{64}$", type: "string" }
            },
            required: ["classification", "id", "kind", "path", "sha256"],
            type: "object"
          },
          minItems: 1,
          type: "array"
        },
        federation: { type: "object" },
        manifestVersion: { const: "1.0.0" },
        productVersion: { const: "0.1.1" },
        sourceRoot: { const: "public-src" }
      }
    ),
    "receipt.schema.json": schema(
      `${base}/receipt.schema.json`,
      "Hive Hub append-only receipt",
      [
        "$schema",
        "actor",
        "event",
        "kind",
        "ledger",
        "occurredAt",
        "operation",
        "previous",
        "sequence",
        "subject"
      ],
      {
        $schema: httpsUrl,
        actor: nonEmptyString,
        event: nonEmptyString,
        kind: { const: "receipt" },
        ledger: nonEmptyString,
        occurredAt: { format: "date-time", type: "string" },
        operation: { type: "object" },
        previous: { anyOf: [{ type: "null" }, descriptor] },
        sequence: { minimum: 1, type: "integer" },
        subject: descriptor
      }
    ),
    "status.schema.json": schema(
      `${base}/status.schema.json`,
      "Hive Hub static snapshot status",
      ["$schema", "generatedAt", "kind", "mode", "status"],
      {
        $schema: httpsUrl,
        generatedAt: { format: "date-time", type: "string" },
        kind: { const: "status" },
        mode: { const: "static-snapshot" },
        status: { enum: ["operational", "degraded", "withdrawn"] }
      }
    )
  };
}
