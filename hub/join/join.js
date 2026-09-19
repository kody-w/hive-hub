(() => {
  "use strict";

  const capturedFragment = window.location.hash;
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  void verifyAndRender(capturedFragment);

  async function verifyAndRender(fragment) {
    const status = document.getElementById("status");
    const failure = document.getElementById("failure");
    try {
      if (!fragment) {
        status.textContent = "No join card supplied. Choose a public example or use a privately shared locator with your AI.";
        document.getElementById("join-help").hidden = false;
        return;
      }
      const envelope = decodeEnvelope(fragment);
      status.textContent = "Verifying the content-addressed card…";
      const card = await fetchVerifiedJson(envelope.card, "sha256:" + envelope.sha256);
      if (card.kind === "ai-join-card" && card.schema_version === 1) {
        await assertCoreAiCard(card);
        const result = {
          card,
          verification: {
            algorithm: "sha256",
            card: "verified",
            coreContract: "verified",
            verifiedAt: null
          }
        };
        const mode = new URLSearchParams(window.location.search).get("format");
        if (mode === "json" || mode === "llms") {
          renderPlainText(JSON.stringify(result, null, 2) + "\n", "application/json");
          return;
        }
        document.getElementById("machine-readable").textContent = JSON.stringify(result, null, 2);
        document.getElementById("machine-section").hidden = false;
        status.textContent = "Core camera-AI join card verified. Pass the exact JSON to the Hive Hub skill.";
        return;
      }
      assertPublicCard(card);

      status.textContent = "Verifying the Dial Record and every declared protocol document…";
      const [record, protocol, learningBundle, adapter, conformance, hashes] = await Promise.all([
        fetchVerifiedDescriptor(card.record),
        fetchVerifiedDescriptor(card.protocol),
        fetchVerifiedDescriptor(card.learningBundle),
        fetchVerifiedDescriptor(card.adapter),
        fetchVerifiedDescriptor(card.conformance),
        fetchJson(card.api.hashes)
      ]);
      assertBoundedRecord(record);
      assertCardBindings(card, record);
      assertDeclaredDocuments(protocol, learningBundle, adapter, conformance);
      assertHashManifest(hashes, [card.record, card.protocol, card.learningBundle, card.adapter, card.conformance]);
      const seed = card.seed ? await fetchVerifiedDescriptor(card.seed) : null;
      if (seed) {
        if (
          record.locator?.provider !== "static-seed" ||
          card.seed.ref !== record.locator.seed?.ref ||
          seed.kind !== "organization-seed" ||
          seed.status !== "seed-not-activated" ||
          seed.activation?.grantsAuthority !== false ||
          seed.archive?.ref !== record.locator.archive?.ref
        ) {
          throw new Error("The card, record, and organization seed disagree.");
        }
        assertHashManifest(hashes, [card.seed, seed.archive]);
        sameOriginUrl(seed.archive.url);
      }

      const result = {
        adapter,
        card,
        conformance,
        learningBundle,
        protocol,
        record,
        ...(seed ? { seed } : {}),
        verification: {
          algorithm: "sha256",
          card: "verified",
          contentObjects: "verified",
          hashManifestCrossCheck: "verified",
          verifiedAt: null
        }
      };

      const mode = new URLSearchParams(window.location.search).get("format");
      if (mode === "json") {
        renderPlainText(JSON.stringify(result, null, 2) + "\n", "application/json");
        return;
      }
      if (mode === "llms") {
        const response = await fetch(card.api.llms, requestOptions());
        if (!response.ok) {
          throw new Error("Could not load llms.txt");
        }
        renderPlainText(await response.text(), "text/plain");
        return;
      }

      document.getElementById("verified-title").textContent = card.title;
      document.getElementById("summary").textContent = record.summary;
      const steps = document.getElementById("steps");
      for (const instruction of card.steps) {
        const item = document.createElement("li");
        item.textContent = instruction;
        steps.append(item);
      }
      const repositoryLink = document.getElementById("repository-link");
      repositoryLink.href = seed ? seed.archive.url : record.locator.browseUrl;
      if (seed) {
        repositoryLink.textContent = "Download hash-pinned organization seed";
        repositoryLink.download = seed.slug + ".zip";
      }
      const encodedFragment = "#v1." + encodeBase64Url(JSON.stringify(envelope));
      const jsonLink = document.getElementById("json-link");
      jsonLink.href = window.location.pathname + "?format=json" + encodedFragment;
      const llmsLink = document.getElementById("llms-link");
      llmsLink.href = window.location.pathname + "?format=llms" + encodedFragment;
      document.getElementById("machine-readable").textContent = JSON.stringify(result, null, 2);
      document.getElementById("verified").hidden = false;
      document.getElementById("machine-section").hidden = false;
      status.textContent = "Verification complete. Locator claims remain bounded by the displayed declarations.";
    } catch (error) {
      status.textContent = "Verification failed.";
      failure.textContent = error instanceof Error ? error.message : "Unknown verification error";
      failure.hidden = false;
    }
  }

  function decodeEnvelope(fragment) {
    if (!fragment.startsWith("#v1.")) {
      throw new Error("This page needs a versioned locator fragment from a Hive Hub join card.");
    }
    const encoded = fragment.slice(4);
    let envelope;
    try {
      envelope = JSON.parse(decodeBase64Url(encoded));
    } catch {
      throw new Error("The locator fragment is not valid version 1 JSON.");
    }
    const keys = Object.keys(envelope).sort().join(",");
    if (keys !== "card,sha256,v" || envelope.v !== 1 || !/^[a-f0-9]{64}$/.test(envelope.sha256)) {
      throw new Error("The locator fragment contains unsupported or invalid fields.");
    }
    const cardUrl = sameOriginUrl(envelope.card);
    return { card: cardUrl.href, sha256: envelope.sha256, v: 1 };
  }

  function decodeBase64Url(value) {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const bytes = Uint8Array.from(window.atob(padded), (character) => character.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  }

  function encodeBase64Url(value) {
    const bytes = new TextEncoder().encode(value);
    let binary = "";
    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }
    return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  function sameOriginUrl(value) {
    const url = new URL(value, window.location.href);
    if (url.origin !== window.location.origin || url.username || url.password) {
      throw new Error("Join cards may fetch only credential-free, same-origin static files.");
    }
    return url;
  }

  function requestOptions() {
    return {
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      referrerPolicy: "no-referrer"
    };
  }

  async function fetchBytes(value) {
    const url = sameOriginUrl(value);
    const response = await fetch(url, requestOptions());
    if (!response.ok) {
      throw new Error("Static object could not be fetched: " + url.pathname);
    }
    return new Uint8Array(await response.arrayBuffer());
  }

  async function fetchJson(value) {
    const bytes = await fetchBytes(value);
    try {
      return JSON.parse(new TextDecoder().decode(bytes));
    } catch {
      throw new Error("Static object is not valid JSON.");
    }
  }

  async function fetchVerifiedJson(value, expectedRef) {
    const bytes = await fetchBytes(value);
    const actualRef = "sha256:" + bytesToHex(await window.crypto.subtle.digest("SHA-256", bytes));
    if (actualRef !== expectedRef) {
      throw new Error("Content hash mismatch for " + new URL(value).pathname);
    }
    try {
      return JSON.parse(new TextDecoder().decode(bytes));
    } catch {
      throw new Error("Verified bytes are not valid JSON.");
    }
  }

  function fetchVerifiedDescriptor(descriptor) {
    if (!descriptor || typeof descriptor.url !== "string" || typeof descriptor.ref !== "string") {
      throw new Error("A content descriptor is incomplete.");
    }
    return fetchVerifiedJson(descriptor.url, descriptor.ref);
  }

  function bytesToHex(buffer) {
    return Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function assertCoreAiCard(card) {
    const keys = Object.keys(card).sort().join(",");
    if (
      keys !== "adapter_plan,card_id,expected_protocol_fingerprint,expected_record_id,issued_at,kind,locator,principal,schema_version" ||
      card.adapter_plan !== null ||
      card.expected_record_id !== null ||
      card.expected_protocol_fingerprint !== null ||
      !card.principal ||
      !["human", "ai"].includes(card.principal.kind) ||
      typeof card.principal.id !== "string" ||
      typeof card.locator !== "string"
    ) {
      throw new Error("The verified object is not a supported closed core AI join card.");
    }
    const body = {
      adapter_plan: null,
      expected_protocol_fingerprint: null,
      expected_record_id: null,
      issued_at: card.issued_at,
      kind: "ai-join-card-body",
      locator: card.locator,
      principal: card.principal,
      schema_version: 1
    };
    const bytes = new TextEncoder().encode(canonicalString(body));
    const digest = bytesToHex(await window.crypto.subtle.digest("SHA-256", bytes));
    if (card.card_id !== "urn:hivehub:sha256:" + digest) {
      throw new Error("The core AI join card id does not match its canonical body.");
    }
  }

  function canonicalString(value) {
    if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
      return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
      return "[" + value.map(canonicalString).join(",") + "]";
    }
    return "{" + Object.keys(value).sort().map((key) =>
      JSON.stringify(key) + ":" + canonicalString(value[key])
    ).join(",") + "}";
  }

  function assertPublicCard(card) {
    if (
      card.kind !== "ai-join-card" ||
      card.classification !== "public-locator-only" ||
      !Array.isArray(card.steps)
    ) {
      throw new Error("The verified object is not a public locator-only AI join card.");
    }
  }

  function assertBoundedRecord(record) {
    if (
      record.kind !== "dial-record" ||
      record.visibility !== "public" ||
      !Array.isArray(record.claims?.authority) ||
      record.claims.authority.length !== 0 ||
      !Array.isArray(record.claims?.semanticCompatibility) ||
      record.claims.semanticCompatibility.length !== 0
    ) {
      throw new Error("The Dial Record exceeds public locator-only claim boundaries.");
    }
  }

  function assertCardBindings(card, record) {
    for (const field of ["protocol", "learningBundle", "adapter", "conformance"]) {
      if (card[field]?.ref !== record[field]?.ref || card[field]?.path !== record[field]?.path) {
        throw new Error("The join card and Dial Record disagree about " + field + ".");
      }
    }
    if (record.protocolFingerprint !== record.protocol.ref) {
      throw new Error("The Dial Record protocol fingerprint is not exact.");
    }
  }

  function assertDeclaredDocuments(protocol, learningBundle, adapter, conformance) {
    if (
      protocol.kind !== "protocol-declaration" ||
      learningBundle.kind !== "learning-bundle" ||
      adapter.kind !== "adapter-declaration" ||
      conformance.kind !== "conformance-contract" ||
      adapter.executable !== false
    ) {
      throw new Error("One or more declared protocol documents has an invalid kind or activation state.");
    }
  }

  function assertHashManifest(manifest, descriptors) {
    if (manifest.kind !== "hash-manifest" || manifest.algorithm !== "sha256") {
      throw new Error("The static hash manifest is invalid.");
    }
    for (const descriptor of descriptors) {
      const entry = manifest.files?.[descriptor.path];
      if (!entry || "sha256:" + entry.sha256 !== descriptor.ref) {
        throw new Error("The hash manifest does not cross-check " + descriptor.path);
      }
    }
  }

  function renderPlainText(value, type) {
    document.documentElement.removeAttribute("class");
    document.body.textContent = value;
    document.body.className = "plain-output";
    document.title = type;
  }
})();
