# Governance Evidence Signing

OpenDataGraph v1.7 can sign the canonical manifest of every governance evidence package and verify the package independently of its storage location. Signing covers the payload digest, each section digest, package identity, tenant, window, categories, record count, truncation state, and generator version.

## Package assurance model

Package format version 2 contains:

- a canonical `manifest` with SHA-256 digests;
- metadata-only `analytics` and bounded `records` payloads;
- an `assurance` object containing the signature type, key identity, public verification material or Sigstore bundle, and signature.

Verification recomputes every section and payload digest before validating the manifest signature. A cryptographically valid signature is reported separately from trust. Trust requires an explicitly selected verification profile whose key identity and fingerprint, public key, or Sigstore certificate identity matches the package.

## Signing profiles

Configure named profiles in `ODG_GOVERNANCE_PACKAGE_SIGNING_PROFILES_JSON`. Do not place private keys or tokens in JSON; use `env:` or `file:` references under approved secret roots.

Ed25519 example:

```json
{
  "audit-release": {
    "type": "ed25519",
    "key_id": "audit-release-2026-07",
    "private_key_ref": "file:/run/secrets/opendatagraph/audit-signing.pem"
  }
}
```

AWS KMS example:

```json
{
  "audit-kms": {
    "type": "aws-kms",
    "key_id": "arn:aws:kms:us-west-2:111122223333:key/example",
    "signing_algorithm": "ECDSA_SHA_256",
    "region": "us-west-2",
    "workload_exchange_profile": "aws-audit"
  }
}
```

Sigstore keyless profiles require `certificate_identity`, `certificate_oidc_issuer`, and `identity_token_ref`. The configured `ODG_COSIGN_EXECUTABLE` must provide compatible `sign-blob` and offline `verify-blob` commands. Tokens are resolved only during signing and are not added to the package.

Set `ODG_GOVERNANCE_PACKAGE_DEFAULT_SIGNING_PROFILE` to select the default profile. Set `ODG_GOVERNANCE_PACKAGE_SIGNING_REQUIRED=true` to reject package creation when no signing profile is selected.

## Verification profiles

Configure trust separately in `ODG_GOVERNANCE_PACKAGE_VERIFICATION_PROFILES_JSON`.

```json
{
  "audit-release": {
    "type": "ed25519",
    "key_id": "audit-release-2026-07",
    "public_key_ref": "file:/run/secrets/opendatagraph/audit-signing-public.pem"
  }
}
```

Public-key profiles may use `public_key_sha256` instead of a PEM reference. AWS KMS packages are verified locally against the public key embedded in the package, then trusted only when the verification profile matches its configured key and fingerprint. Sigstore profiles pin both certificate identity and OIDC issuer and verify the bundle offline.

## Verification

Auditors can verify a stored package with:

```text
POST /api/v1/governance/evidence-packages/{package_id}/verify
```

The request accepts optional `verification_profile`. The response distinguishes `valid`, `signature_valid`, and `trusted` and returns bounded reason codes without exposing key material.

Verify a downloaded package independently:

```bash
python -m app.evidence_verify package.json \
  --profile audit-release \
  --require-trusted
```

The command exits non-zero for digest or signature failure and, with `--require-trusted`, for an untrusted signer.

## Key operations

- Keep signing and verification profiles independently managed.
- Grant KMS signing permission only to package workers and public-key read permission only when needed.
- Rotate by adding a new profile and retaining old public verification profiles for the evidence retention period.
- Keep package storage private and immutable where required; signatures detect tampering but do not provide retention enforcement.
- Record verification output with the receiving audit workflow rather than modifying the package.
