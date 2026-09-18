import { createHash } from "node:crypto";

export const CHANT_PROTOCOL = "hive-hub-chant/1";
export const CHANT_VOCABULARY_SHA256 =
  "325f47d38851721f16cf111f80114d8d9146e84813fa6822fe2ad38dd18dbb36";
export const CHANT_VOCABULARY_PROVENANCE =
  "kody-w/rappid@c988d7975dadb6a8f055183cdbc4cbb17adfe2ae";
export const CHANT_WORDS = Object.freeze([
  "ember",
  "hollow",
  "quartz",
  "tidal",
  "vessel",
  "marrow",
  "lantern",
  "thicket",
  "basalt",
  "cinder",
  "willow",
  "fathom",
  "granite",
  "sable",
  "harbor",
  "kestrel",
  "amber",
  "furrow",
  "lichen",
  "brindle",
  "aspen",
  "bramble",
  "cobalt",
  "drift",
  "eddy",
  "fenlark",
  "gully",
  "heron",
  "inkcap",
  "juniper",
  "knoll",
  "loam",
  "mica",
  "nettle",
  "osprey",
  "petrel",
  "quill",
  "rushes",
  "shale",
  "tarn",
  "umber",
  "vale",
  "wren",
  "yarrow",
  "zephyr",
  "alder",
  "briar",
  "cairn",
  "dune",
  "elm",
  "flint",
  "gorse",
  "hazel",
  "iris",
  "jetty",
  "kelp",
  "larch",
  "moss",
  "north",
  "otter",
  "pine",
  "quarry",
  "reed",
  "spruce",
  "thorn",
  "upland",
  "vetch",
  "wharf",
  "yew",
  "arbor",
  "birch",
  "cedar",
  "delta",
  "ester",
  "fjord",
  "glade",
  "heath",
  "islet",
  "jasper",
  "karst",
  "ledge",
  "mesa",
  "nadir",
  "oxbow",
  "prairie",
  "quiver",
  "ridge",
  "steppe",
  "trench",
  "ursa",
  "verge",
  "wold",
  "xenia",
  "yonder",
  "zenith",
  "anvil",
  "bluff",
  "crag",
  "dell",
  "ebb",
  "ford",
  "grove",
  "hearth",
  "ivy",
  "jade",
  "kiln",
  "lark",
  "mire",
  "nook",
  "orchid",
  "pond",
  "quay",
  "rill",
  "sedge",
  "tor",
  "usher",
  "vine",
  "weir",
  "xylem",
  "yield",
  "zeal",
  "atlas",
  "beacon",
  "cove",
  "dusk",
  "frost",
  "gale",
  "haven"
]);

const CHANT_WORD_SET = new Set(CHANT_WORDS);
const DIAL_ID = /^dial:sha256:[a-f0-9]{64}$/;

if (CHANT_WORDS.length !== 128 || CHANT_WORD_SET.size !== 128) {
  throw new Error("Hive Hub chant vocabulary must contain 128 unique words");
}
if (
  createHash("sha256").update(CHANT_WORDS.join("\n"), "utf8").digest("hex") !==
  CHANT_VOCABULARY_SHA256
) {
  throw new Error("Hive Hub chant vocabulary hash mismatch");
}

export function normalizeChant(value) {
  if (typeof value !== "string" || Buffer.byteLength(value, "utf8") > 512) {
    throw new Error("Chant must be a bounded string");
  }
  const normalized = value.normalize("NFKC").toLowerCase().trim();
  let words;
  if (normalized.includes("-")) {
    if (/\s/.test(normalized)) {
      throw new Error("Chant must use spaces or canonical hyphens, not both");
    }
    words = normalized.split("-");
  } else {
    words = normalized.split(/\s+/);
  }
  if (words.length !== 7 || words.some((word) => !CHANT_WORD_SET.has(word))) {
    throw new Error("Chant must contain exactly seven frozen vocabulary words");
  }
  return words.join("-");
}

export function deriveChant(dialRecordId) {
  if (typeof dialRecordId !== "string" || !DIAL_ID.test(dialRecordId)) {
    throw new Error("Dial Record ID must be a full canonical dial:sha256 value");
  }
  const digest = createHash("sha256").update(dialRecordId, "utf8").digest();
  return [...digest.subarray(0, 7)]
    .map((byte) => CHANT_WORDS[byte % 128])
    .join("-");
}

export function verifyChant(dialRecordId, chant) {
  const normalized = normalizeChant(chant);
  if (normalized !== deriveChant(dialRecordId)) {
    throw new Error("Chant does not match the full Dial Record ID");
  }
  return normalized;
}
