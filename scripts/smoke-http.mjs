import { createHash } from "node:crypto";

import { deriveChant } from "./lib/chant.mjs";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function canonical(value) {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonical).join(",")}]`;
  }
  return `{${Object.keys(value)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
    .join(",")}}`;
}

async function get(base, relative) {
  const response = await fetch(new URL(relative, base), {
    cache: "no-store",
    credentials: "omit",
    redirect: "error"
  });
  assert(response.ok, `${relative} returned ${response.status}`);
  return response;
}

async function main() {
  const index = process.argv.indexOf("--base");
  if (index < 0 || !process.argv[index + 1]) {
    throw new Error("usage: node scripts/smoke-http.mjs --base http://127.0.0.1:PORT/");
  }
  const base = new URL(process.argv[index + 1]);
  assert(base.protocol === "http:" || base.protocol === "https:", "base must use HTTP");

  const wellKnown = await (await get(base, ".well-known/hive-hub.json")).json();
  const releaseIndex = await (await get(base, "api/hive-hub/v1/release.json")).json();
  const release = await (await get(base, releaseIndex.current.path)).json();
  const dialbook = await (await get(base, "api/hive-hub/v1/dialbook.json")).json();
  const cards = await (await get(base, "api/hive-hub/v1/cards/index.json")).json();
  const card = await (await get(base, cards.cards[0].card.path)).json();
  const joinHtml = await (await get(base, "hub/join/")).text();
  const joinInstructions = await (await get(base, "hub/join/ai.json")).json();
  const coreCardResponse = await get(
    base,
    joinInstructions.cameraAiCard.path
  );
  const coreCardBytes = new Uint8Array(await coreCardResponse.arrayBuffer());
  const cardDigest = createHash("sha256").update(coreCardBytes).digest("hex");
  assert(
    `sha256:${cardDigest}` === joinInstructions.cameraAiCard.ref,
    "camera AI card content reference failed"
  );
  const coreCard = JSON.parse(new TextDecoder().decode(coreCardBytes));
  const body = {
    adapter_plan: null,
    expected_protocol_fingerprint: null,
    expected_record_id: null,
    issued_at: coreCard.issued_at,
    kind: "ai-join-card-body",
    locator: coreCard.locator,
    principal: coreCard.principal,
    schema_version: 1
  };
  const bodyDigest = createHash("sha256").update(canonical(body)).digest("hex");
  assert(coreCard.card_id === `urn:hivehub:sha256:${bodyDigest}`, "core card id failed");
  assert(card.dialId === coreCard.locator, "public card and core locator disagree");
  assert(card.chant.value === deriveChant(card.dialId), "public card chant derivation failed");
  assert(
    dialbook.chants[card.chant.value].some((candidate) => candidate.ref === card.record.ref),
    "public dialbook does not index the derived chant"
  );
  assert(
    !Object.prototype.hasOwnProperty.call(dialbook.chants, "hive-hub-public-lab"),
    "repository slug leaked into the chant index"
  );
  assert(release.version === "0.1.1", "release version failed");
  assert(wellKnown.release.ref === releaseIndex.current.ref, "well-known release link failed");
  assert(
    joinHtml.includes('data-verification-warning="required"'),
    "join page is missing its verify-before-you-join warning"
  );
  process.stdout.write("local HTTP static smoke passed\n");
}

main().catch((error) => {
  process.stderr.write(`${error.stack ?? error.message}\n`);
  process.exitCode = 1;
});
