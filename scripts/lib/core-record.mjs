import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { canonicalJson, sha256Bytes } from "./canonical.mjs";
import { deriveChant } from "./chant.mjs";

export function projectCoreRecord(record, contracts) {
  const result = spawnSync(
    process.env.PYTHON || "python3",
    ["-B", fileURLToPath(new URL("../project_published_record.py", import.meta.url))],
    {
      encoding: "utf8",
      input: canonicalJson({ record, ...contracts }),
      maxBuffer: 2 * 1024 * 1024,
      timeout: 30_000
    }
  );
  if (result.error || result.status !== 0) {
    throw new Error(`Core projection failed: ${result.error?.message || result.stderr}`);
  }
  const projection = JSON.parse(result.stdout);
  const dialId = projection.coreRecord.id.replace(/^urn:hivehub:/, "dial:");
  const document = {
    ...record,
    ...projection,
    dialId,
    chants: [{ role: "candidate-locator-only", value: deriveChant(dialId) }]
  };
  assertCoreIdentity(document);
  return document;
}

export function assertCoreIdentity(record) {
  const core = record.coreRecord;
  if (!core || core.kind !== "dial-record" || core.schema_version !== 1) {
    throw new Error("Published record must carry a core DialRecord");
  }
  const { id, ...fields } = core;
  const body = { ...fields, kind: "dial-record-body" };
  const digest = sha256Bytes(Buffer.from(canonicalJson(body).slice(0, -1)));
  if (id !== `urn:hivehub:sha256:${digest}` || record.dialId !== `dial:sha256:${digest}`) {
    throw new Error("Published Dial Record ID does not match the core identity body");
  }
  if (
    record.chants.length !== 1 ||
    record.chants[0].role !== "candidate-locator-only" ||
    record.chants[0].value !== deriveChant(record.dialId)
  ) {
    throw new Error("Published chant does not match the core Dial Record ID");
  }
}
