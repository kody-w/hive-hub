import { createHash } from "node:crypto";
import { mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";

export const PUBLIC_ROOT_PATHS = [
  ".nojekyll",
  ".well-known/hive-hub.json",
  "api/hive-hub/v1",
  "hub",
  "index.html",
  "llms.txt"
];

function serialize(value) {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new TypeError("Canonical JSON does not permit non-finite numbers");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(serialize).join(",")}]`;
  }
  if (typeof value === "object") {
    const pairs = Object.keys(value)
      .sort()
      .map((key) => {
        if (value[key] === undefined) {
          throw new TypeError(`Canonical JSON does not permit undefined at ${key}`);
        }
        return `${JSON.stringify(key)}:${serialize(value[key])}`;
      });
    return `{${pairs.join(",")}}`;
  }
  throw new TypeError(`Canonical JSON cannot serialize ${typeof value}`);
}

export function canonicalJson(value) {
  return `${serialize(value)}\n`;
}

export function sha256Bytes(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

export function sha256Json(value) {
  return sha256Bytes(Buffer.from(canonicalJson(value)));
}

export function contentRef(digest) {
  if (!/^[a-f0-9]{64}$/.test(digest)) {
    throw new TypeError(`Invalid SHA-256 digest: ${digest}`);
  }
  return `sha256:${digest}`;
}

export function digestFromRef(ref) {
  const match = /^sha256:([a-f0-9]{64})$/.exec(ref);
  if (!match) {
    throw new TypeError(`Invalid content reference: ${ref}`);
  }
  return match[1];
}

export function base64url(value) {
  return Buffer.from(value).toString("base64url");
}

export function parseCliArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      throw new Error(`Unexpected argument: ${token}`);
    }
    const name = token.slice(2);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) {
      throw new Error(`Missing value for --${name}`);
    }
    result[name] = value;
    index += 1;
  }
  return result;
}

export function normalizeRelativePath(value) {
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError("Expected a non-empty relative path");
  }
  if (value.includes("\\") || path.posix.isAbsolute(value)) {
    throw new Error(`Path must be relative POSIX syntax: ${value}`);
  }
  const normalized = path.posix.normalize(value);
  if (normalized !== value || normalized === ".." || normalized.startsWith("../")) {
    throw new Error(`Path escapes its root: ${value}`);
  }
  return normalized;
}

export function resolveInside(root, relativePath) {
  const normalized = normalizeRelativePath(relativePath);
  const resolvedRoot = path.resolve(root);
  const resolved = path.resolve(resolvedRoot, ...normalized.split("/"));
  if (resolved !== resolvedRoot && !resolved.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw new Error(`Path escapes output root: ${relativePath}`);
  }
  return resolved;
}

export async function removePublicSurface(root) {
  const resolvedRoot = path.resolve(root);
  await Promise.all(
    PUBLIC_ROOT_PATHS.map(async (relativePath) => {
      const target = resolveInside(resolvedRoot, relativePath);
      await rm(target, { force: true, recursive: true });
    })
  );
}

export class OutputWriter {
  constructor(root) {
    this.root = path.resolve(root);
    this.files = new Map();
  }

  async write(relativePath, content) {
    const normalized = normalizeRelativePath(relativePath);
    const bytes = Buffer.isBuffer(content) ? content : Buffer.from(content);
    const existing = this.files.get(normalized);
    if (existing) {
      if (!existing.equals(bytes)) {
        throw new Error(`Conflicting duplicate output path: ${normalized}`);
      }
      return {
        bytes: existing.length,
        digest: sha256Bytes(existing),
        path: normalized
      };
    }
    const target = resolveInside(this.root, normalized);
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, bytes);
    this.files.set(normalized, bytes);
    return {
      bytes: bytes.length,
      digest: sha256Bytes(bytes),
      path: normalized
    };
  }

  async writeJson(relativePath, value) {
    return this.write(relativePath, canonicalJson(value));
  }
}

async function walkDirectory(root, relativeDirectory, output) {
  const { readdir } = await import("node:fs/promises");
  const directory = resolveInside(root, relativeDirectory);
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") {
      return;
    }
    throw error;
  }
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    const relativePath = path.posix.join(relativeDirectory, entry.name);
    if (entry.isDirectory()) {
      await walkDirectory(root, relativePath, output);
    } else if (entry.isFile()) {
      output.push(relativePath);
    } else {
      throw new Error(`Public output may not contain special files: ${relativePath}`);
    }
  }
}

export async function listPublicFiles(root) {
  const resolvedRoot = path.resolve(root);
  const files = [];
  for (const publicPath of PUBLIC_ROOT_PATHS) {
    const target = resolveInside(resolvedRoot, publicPath);
    let targetStat;
    try {
      targetStat = await stat(target);
    } catch (error) {
      if (error.code === "ENOENT") {
        continue;
      }
      throw error;
    }
    if (targetStat.isDirectory()) {
      await walkDirectory(resolvedRoot, publicPath, files);
    } else if (targetStat.isFile()) {
      files.push(publicPath);
    }
  }
  return [...new Set(files)].sort();
}

export async function readPublicFile(root, relativePath) {
  return readFile(resolveInside(root, relativePath));
}

export function publicUrl(baseUrl, relativePath) {
  const normalizedBase = baseUrl.replace(/\/+$/, "");
  return `${normalizedBase}/${normalizeRelativePath(relativePath)}`;
}

export function toPosixRelative(from, to) {
  return path.relative(from, to).split(path.sep).join("/");
}

export function isMain(importMetaUrl) {
  return process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(importMetaUrl).pathname);
}
