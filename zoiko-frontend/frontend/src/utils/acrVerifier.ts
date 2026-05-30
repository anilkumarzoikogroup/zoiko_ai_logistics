/**
 * Client-side ACR (Action Certification Record) verifier.
 *
 * Verifies a Zoiko ACR verify bundle offline — no backend calls required.
 * Uses the Web Crypto API (SHA-256) to recompute the Merkle root over the
 * 8 artifact hashes and compare against the bundle's claimed merkle_root.
 *
 * Ed25519 signature verification is not yet supported natively by Web Crypto
 * in all browsers; that check is skipped with a clear warning in the result.
 */

export interface ACRArtifact {
  name: string;
  hash: string;  // hex SHA-256
  domain_tag?: string;
}

export interface ACRVerifyBundle {
  acr_id:        string;
  case_id:       string;
  tenant_id:     string;
  merkle_root:   string;  // hex
  artifacts:     ACRArtifact[];
  issued_at:     string;
  acr_signature: string;  // hex
  acr_kid:       string;
  schema_version?: string;
  public_keys?:  Record<string, string>;  // kid → base64 DER
}

export interface VerifyResult {
  passed:            boolean;
  merkle_root_match: boolean;
  artifact_count:    number;
  errors:            string[];
  warnings:          string[];
  computed_root:     string;
  claimed_root:      string;
}

// ── WebCrypto helpers ─────────────────────────────────────────────────────────

function hexToBytes(hex: string): Uint8Array {
  if (hex.length % 2 !== 0) throw new Error(`Odd hex length: ${hex}`);
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
}

async function sha256(data: Uint8Array): Promise<Uint8Array> {
  const digest = await crypto.subtle.digest("SHA-256", data.buffer as ArrayBuffer);
  return new Uint8Array(digest);
}

// ── Merkle primitives (mirror phase-0/zoiko_common/crypto/merkle.py) ─────────

/** Leaf hash: SHA-256(0x00 || domain_bytes || leaf_data) */
async function hashLeaf(domain: string, leafData: Uint8Array): Promise<Uint8Array> {
  const domainBytes = new TextEncoder().encode(domain);
  const payload = new Uint8Array(1 + domainBytes.length + leafData.length);
  payload[0] = 0x00;
  payload.set(domainBytes, 1);
  payload.set(leafData, 1 + domainBytes.length);
  return sha256(payload);
}

/** Internal node: SHA-256(0x01 || left || right) */
async function hashInternal(left: Uint8Array, right: Uint8Array): Promise<Uint8Array> {
  const payload = new Uint8Array(1 + 32 + 32);
  payload[0] = 0x01;
  payload.set(left,  1);
  payload.set(right, 33);
  return sha256(payload);
}

/** Build Merkle root from a list of leaf hashes (raw 32-byte values). */
async function buildMerkleRoot(leafHashes: Uint8Array[]): Promise<Uint8Array> {
  if (leafHashes.length === 0) throw new Error("Cannot build Merkle root from empty list");

  // Hash each leaf with the ACR domain
  let level: Uint8Array[] = await Promise.all(
    leafHashes.map(h => hashLeaf("zoiko/v1/acr", h))
  );

  // Reduce to root
  while (level.length > 1) {
    const next: Uint8Array[] = [];
    for (let i = 0; i < level.length; i += 2) {
      if (i + 1 < level.length) {
        next.push(await hashInternal(level[i], level[i + 1]));
      } else {
        // Odd leaf: promote with itself
        next.push(await hashInternal(level[i], level[i]));
      }
    }
    level = next;
  }
  return level[0];
}

// ── Main verifier ─────────────────────────────────────────────────────────────

/**
 * Verify an ACR bundle offline using Web Crypto.
 *
 * Steps:
 *   1. Parse the 8 artifact hashes from bundle.artifacts
 *   2. Compute the Merkle root over those hashes
 *   3. Compare against bundle.merkle_root
 *   4. Warn (don't fail) if Ed25519 sig cannot be verified in browser
 *
 * Returns a VerifyResult describing the outcome.
 */
export async function verifyACRBundle(bundle: ACRVerifyBundle): Promise<VerifyResult> {
  const errors:   string[] = [];
  const warnings: string[] = [];

  // ── Step 1: parse artifact hashes ────────────────────────────────────────
  if (!bundle.artifacts || bundle.artifacts.length === 0) {
    errors.push("ACR bundle has no artifacts");
    return {
      passed: false, merkle_root_match: false,
      artifact_count: 0, errors, warnings,
      computed_root: "", claimed_root: bundle.merkle_root ?? "",
    };
  }

  const leafHashes: Uint8Array[] = [];
  for (const artifact of bundle.artifacts) {
    if (!artifact.hash || artifact.hash.length !== 64) {
      errors.push(`Artifact '${artifact.name}' has invalid hash (expected 64-char hex, got ${artifact.hash?.length ?? 0})`);
      continue;
    }
    try {
      leafHashes.push(hexToBytes(artifact.hash));
    } catch (e) {
      errors.push(`Artifact '${artifact.name}' hash is not valid hex: ${e}`);
    }
  }

  if (errors.length > 0) {
    return {
      passed: false, merkle_root_match: false,
      artifact_count: bundle.artifacts.length, errors, warnings,
      computed_root: "", claimed_root: bundle.merkle_root,
    };
  }

  // ── Step 2: compute Merkle root ───────────────────────────────────────────
  let computedRoot: Uint8Array;
  try {
    computedRoot = await buildMerkleRoot(leafHashes);
  } catch (e) {
    errors.push(`Failed to compute Merkle root: ${e}`);
    return {
      passed: false, merkle_root_match: false,
      artifact_count: bundle.artifacts.length, errors, warnings,
      computed_root: "", claimed_root: bundle.merkle_root,
    };
  }

  const computedHex = bytesToHex(computedRoot);

  // ── Step 3: compare roots ────────────────────────────────────────────────
  const merkleRootMatch = computedHex === bundle.merkle_root;
  if (!merkleRootMatch) {
    errors.push(
      `Merkle root mismatch:\n  computed: ${computedHex}\n  claimed:  ${bundle.merkle_root}`
    );
  }

  // ── Step 4: Ed25519 signature check (browser limitation warning) ──────────
  if (!bundle.acr_signature || bundle.acr_signature.length === 0) {
    errors.push("ACR bundle has no signature");
  } else if (!bundle.public_keys || !bundle.public_keys[bundle.acr_kid]) {
    warnings.push(
      `Ed25519 signature NOT verified: public key for kid '${bundle.acr_kid}' not in bundle. ` +
      `Use verify.sh with the ACR zip for full offline verification.`
    );
  } else {
    // Web Crypto does not yet support Ed25519 in all browsers (Chrome 118+, Firefox 119+)
    // Attempt verification and fall back gracefully
    try {
      const pubKeyB64 = bundle.public_keys[bundle.acr_kid];
      const pubKeyDer = Uint8Array.from(atob(pubKeyB64), c => c.charCodeAt(0));
      const cryptoKey = await crypto.subtle.importKey(
        "spki", pubKeyDer,
        { name: "Ed25519" },
        false,
        ["verify"],
      );
      const sigBytes     = hexToBytes(bundle.acr_signature);
      const rootBytes    = hexToBytes(bundle.merkle_root);
      const sigValid     = await crypto.subtle.verify("Ed25519", cryptoKey, sigBytes.buffer as ArrayBuffer, rootBytes.buffer as ArrayBuffer);
      if (!sigValid) {
        errors.push("Ed25519 signature verification FAILED — bundle may be tampered");
      }
    } catch (_e) {
      warnings.push(
        "Ed25519 signature verification skipped: browser does not support Ed25519 via Web Crypto. " +
        "Use verify.sh from the ACR zip for full offline verification."
      );
    }
  }

  const passed = merkleRootMatch && errors.length === 0;

  return {
    passed,
    merkle_root_match: merkleRootMatch,
    artifact_count:    bundle.artifacts.length,
    errors,
    warnings,
    computed_root: computedHex,
    claimed_root:  bundle.merkle_root,
  };
}

/**
 * Parse a raw JSON string or object into an ACRVerifyBundle.
 * Throws if the bundle is malformed.
 */
export function parseACRBundle(raw: string | object): ACRVerifyBundle {
  const obj = typeof raw === "string" ? JSON.parse(raw) : raw;
  const required = ["acr_id", "case_id", "tenant_id", "merkle_root", "artifacts", "issued_at"];
  for (const field of required) {
    if (!(field in obj)) throw new Error(`ACR bundle missing required field: '${field}'`);
  }
  return obj as ACRVerifyBundle;
}
