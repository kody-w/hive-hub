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
        api: { type: "object" },
        cardId: nonEmptyString,
        classification: { const: "public-locator-only" },
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
        kind: { const: "dial-record" },
        learningBundle: descriptor,
        locator: { type: "object" },
        protocol: descriptor,
        recordId: nonEmptyString,
        visibility: { const: "public" }
      }
    ),
    "dialbook.schema.json": schema(
      `${base}/dialbook.schema.json`,
      "Hive Hub public dialbook",
      ["$schema", "chants", "kind", "records"],
      {
        $schema: httpsUrl,
        chants: {
          additionalProperties: {
            items: descriptor,
            minItems: 1,
            type: "array"
          },
          type: "object"
        },
        kind: { const: "public-dialbook" },
        records: { items: descriptor, type: "array" }
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
