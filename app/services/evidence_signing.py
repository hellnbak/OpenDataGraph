import base64
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings


SIGNATURE_TYPES = {"ed25519", "aws-kms", "sigstore"}
KMS_ALGORITHMS = {
    "ECDSA_SHA_256",
    "RSASSA_PKCS1_V1_5_SHA_256",
    "RSASSA_PSS_SHA_256",
}


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        default=_json_default,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def signing_profiles() -> dict[str, dict]:
    return _profile_configuration(
        settings.governance_package_signing_profiles_json,
        "ODG_GOVERNANCE_PACKAGE_SIGNING_PROFILES_JSON",
    )


def verification_profiles() -> dict[str, dict]:
    return _profile_configuration(
        settings.governance_package_verification_profiles_json,
        "ODG_GOVERNANCE_PACKAGE_VERIFICATION_PROFILES_JSON",
    )


def validate_signing_profile(profile_name: str | None) -> str | None:
    selected = profile_name or settings.governance_package_default_signing_profile or None
    if selected is None:
        if settings.governance_package_signing_required:
            raise ValueError("A governance evidence signing profile is required")
        return None
    profile = signing_profiles().get(selected)
    if not profile:
        raise ValueError("Governance evidence signing profile is not configured")
    profile_type = profile.get("type")
    if profile_type not in SIGNATURE_TYPES:
        raise ValueError("Governance evidence signing profile type is unsupported")
    if not isinstance(profile.get("key_id"), str) or not profile["key_id"].strip():
        raise ValueError("Governance evidence signing profile key_id is required")
    return selected


def sign_manifest(manifest: dict, profile_name: str | None) -> dict:
    selected = validate_signing_profile(profile_name)
    if selected is None:
        return {
            "status": "unsigned",
            "profile": None,
            "type": "none",
            "key_id": None,
            "signed_at": None,
        }
    profile = signing_profiles()[selected]
    profile_type = profile["type"]
    manifest_bytes = canonical_json(manifest)
    if profile_type == "ed25519":
        assurance = _sign_ed25519(manifest_bytes, profile)
    elif profile_type == "aws-kms":
        assurance = _sign_aws_kms(manifest_bytes, profile)
    else:
        assurance = _sign_sigstore(manifest_bytes, profile)
    return {
        "status": "signed",
        "profile": selected,
        "signed_at": datetime.now(UTC),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        **assurance,
    }


def verify_evidence_package(
    content: bytes,
    verification_profile: str | None = None,
) -> dict:
    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Governance evidence package is not valid JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("Governance evidence package must be a JSON object")
    manifest = document.get("manifest")
    analytics = document.get("analytics")
    records = document.get("records")
    assurance = document.get("assurance")
    if not isinstance(manifest, dict) or not isinstance(records, dict):
        raise ValueError("Governance evidence package manifest or records are invalid")
    if not isinstance(assurance, dict):
        assurance = {
            "status": "unsigned",
            "profile": None,
            "type": "none",
        }
    payload = {"analytics": analytics, "records": records}
    errors = []
    payload_digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    if manifest.get("payload_sha256") != payload_digest:
        errors.append("payload-digest-mismatch")
    expected_sections = manifest.get("section_sha256")
    actual_sections = _section_digests(analytics, records)
    if expected_sections != actual_sections:
        errors.append("section-digest-mismatch")
    manifest_bytes = canonical_json(manifest)
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    if assurance.get("status") == "signed" and assurance.get("manifest_sha256") != manifest_digest:
        errors.append("manifest-digest-mismatch")
    signed = assurance.get("status") == "signed"
    signature_valid = False
    trusted = False
    trust_profile_name = verification_profile or assurance.get("profile")
    trust_profile = _trust_profile(trust_profile_name, verification_profile is not None)
    if signed and not errors:
        signature_valid = _verify_signature(manifest_bytes, assurance)
        trusted = signature_valid and _profile_trusts_assurance(trust_profile, assurance)
        if not signature_valid:
            errors.append("signature-invalid")
    elif not signed and settings.governance_package_signing_required:
        errors.append("signature-required")
    return {
        "valid": not errors,
        "integrity_valid": not any("digest" in error for error in errors),
        "signed": signed,
        "signature_valid": signature_valid,
        "trusted": trusted,
        "signing_profile": assurance.get("profile"),
        "verification_profile": trust_profile_name if trust_profile else None,
        "signature_type": assurance.get("type"),
        "key_id": assurance.get("key_id"),
        "manifest_sha256": manifest_digest,
        "payload_sha256": payload_digest,
        "errors": errors,
    }


def verify_manifest_signature(
    manifest: dict,
    assurance: dict,
    verification_profile: str | None = None,
    require_signature: bool = False,
) -> dict:
    manifest_bytes = canonical_json(manifest)
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    errors = []
    signed = assurance.get("status") == "signed"
    if signed and assurance.get("manifest_sha256") != manifest_digest:
        errors.append("manifest-digest-mismatch")
    signature_valid = False
    trusted = False
    trust_profile_name = verification_profile or assurance.get("profile")
    trust_profile = _trust_profile(
        trust_profile_name,
        verification_profile is not None,
    )
    if signed and not errors:
        signature_valid = _verify_signature(manifest_bytes, assurance)
        trusted = signature_valid and _profile_trusts_assurance(
            trust_profile,
            assurance,
        )
        if not signature_valid:
            errors.append("signature-invalid")
    elif require_signature:
        errors.append("signature-required")
    return {
        "valid": not errors,
        "signed": signed,
        "signature_valid": signature_valid,
        "trusted": trusted,
        "signing_profile": assurance.get("profile"),
        "verification_profile": trust_profile_name if trust_profile else None,
        "signature_type": assurance.get("type"),
        "key_id": assurance.get("key_id"),
        "manifest_sha256": manifest_digest,
        "errors": errors,
    }


def section_digests(analytics: object, records: dict) -> dict[str, str]:
    return _section_digests(analytics, records)


def signing_configuration() -> dict:
    profiles = signing_profiles()
    verification = verification_profiles()
    return {
        "required": settings.governance_package_signing_required,
        "default_profile": settings.governance_package_default_signing_profile or None,
        "signing_profiles": [
            {
                "name": name,
                "type": profile.get("type"),
                "key_id": profile.get("key_id"),
            }
            for name, profile in sorted(profiles.items())
        ],
        "verification_profiles": [
            {
                "name": name,
                "type": profile.get("type"),
                "key_id": profile.get("key_id"),
            }
            for name, profile in sorted(verification.items())
        ],
    }


def _sign_ed25519(manifest_bytes: bytes, profile: dict) -> dict:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    reference = profile.get("private_key_ref")
    if not isinstance(reference, str) or not reference:
        raise ValueError("Ed25519 signing profiles require private_key_ref")
    private_key = serialization.load_pem_private_key(
        _resolve_secret(reference).encode(),
        password=None,
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Governance evidence signing key must be Ed25519")
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "type": "ed25519",
        "algorithm": "Ed25519",
        "key_id": profile["key_id"],
        "signature": _encode(private_key.sign(manifest_bytes)),
        "public_key": _encode(public_der),
        "public_key_sha256": hashlib.sha256(public_der).hexdigest(),
    }


def _sign_aws_kms(manifest_bytes: bytes, profile: dict) -> dict:
    import boto3

    algorithm = profile.get("signing_algorithm", "ECDSA_SHA_256")
    if algorithm not in KMS_ALGORITHMS:
        raise ValueError("AWS KMS governance signing algorithm is unsupported")
    kwargs = {}
    if profile.get("region"):
        kwargs["region_name"] = profile["region"]
    if profile.get("workload_exchange_profile"):
        from app.services.workload_exchange import boto_credentials

        kwargs.update(boto_credentials(profile["workload_exchange_profile"]))
    client = boto3.client("kms", **kwargs)
    key_id = profile["key_id"]
    public_der = client.get_public_key(KeyId=key_id)["PublicKey"]
    response = client.sign(
        KeyId=key_id,
        Message=hashlib.sha256(manifest_bytes).digest(),
        MessageType="DIGEST",
        SigningAlgorithm=algorithm,
    )
    return {
        "type": "aws-kms",
        "algorithm": algorithm,
        "key_id": key_id,
        "signature": _encode(response["Signature"]),
        "public_key": _encode(public_der),
        "public_key_sha256": hashlib.sha256(public_der).hexdigest(),
    }


def _sign_sigstore(manifest_bytes: bytes, profile: dict) -> dict:
    identity = profile.get("certificate_identity")
    issuer = profile.get("certificate_oidc_issuer")
    token_ref = profile.get("identity_token_ref")
    if not all(isinstance(value, str) and value for value in (identity, issuer, token_ref)):
        raise ValueError(
            "Sigstore signing profiles require certificate identity, issuer, and identity_token_ref"
        )
    with tempfile.TemporaryDirectory(prefix="odg-sign-") as directory:
        root = Path(directory)
        manifest_path = root / "manifest.json"
        bundle_path = root / "bundle.sigstore.json"
        manifest_path.write_bytes(manifest_bytes)
        environment = os.environ.copy()
        environment["SIGSTORE_ID_TOKEN"] = _resolve_secret(token_ref)
        command = [
            _cosign_executable(),
            "sign-blob",
            "--yes",
            "--bundle",
            str(bundle_path),
            str(manifest_path),
        ]
        _run_cosign(command, environment)
        try:
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Sigstore did not produce a valid verification bundle") from exc
    return {
        "type": "sigstore",
        "algorithm": "sigstore-bundle",
        "key_id": profile["key_id"],
        "certificate_identity": identity,
        "certificate_oidc_issuer": issuer,
        "bundle": bundle,
    }


def _verify_signature(manifest_bytes: bytes, assurance: dict) -> bool:
    signature_type = assurance.get("type")
    try:
        if signature_type in {"ed25519", "aws-kms"}:
            return _verify_public_key_signature(manifest_bytes, assurance)
        if signature_type == "sigstore":
            return _verify_sigstore(manifest_bytes, assurance)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    return False


def _verify_public_key_signature(manifest_bytes: bytes, assurance: dict) -> bool:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

    public_der = _decode(assurance["public_key"])
    signature = _decode(assurance["signature"])
    if hashlib.sha256(public_der).hexdigest() != assurance.get("public_key_sha256"):
        return False
    public_key = serialization.load_der_public_key(public_der)
    algorithm = assurance.get("algorithm")
    if algorithm == "Ed25519" and isinstance(public_key, ed25519.Ed25519PublicKey):
        public_key.verify(signature, manifest_bytes)
    elif algorithm == "ECDSA_SHA_256" and isinstance(public_key, ec.EllipticCurvePublicKey):
        public_key.verify(signature, manifest_bytes, ec.ECDSA(hashes.SHA256()))
    elif algorithm == "RSASSA_PKCS1_V1_5_SHA_256" and isinstance(public_key, rsa.RSAPublicKey):
        public_key.verify(signature, manifest_bytes, padding.PKCS1v15(), hashes.SHA256())
    elif algorithm == "RSASSA_PSS_SHA_256" and isinstance(public_key, rsa.RSAPublicKey):
        public_key.verify(
            signature,
            manifest_bytes,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
    else:
        return False
    return True


def _verify_sigstore(manifest_bytes: bytes, assurance: dict) -> bool:
    identity = assurance.get("certificate_identity")
    issuer = assurance.get("certificate_oidc_issuer")
    bundle = assurance.get("bundle")
    if not isinstance(identity, str) or not isinstance(issuer, str) or not isinstance(bundle, dict):
        return False
    with tempfile.TemporaryDirectory(prefix="odg-verify-") as directory:
        root = Path(directory)
        manifest_path = root / "manifest.json"
        bundle_path = root / "bundle.sigstore.json"
        manifest_path.write_bytes(manifest_bytes)
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        command = [
            _cosign_executable(),
            "verify-blob",
            "--bundle",
            str(bundle_path),
            "--certificate-identity",
            identity,
            "--certificate-oidc-issuer",
            issuer,
            "--offline=true",
            str(manifest_path),
        ]
        _run_cosign(command, None)
    return True


def _profile_trusts_assurance(profile: dict | None, assurance: dict) -> bool:
    if not profile or profile.get("type") != assurance.get("type"):
        return False
    if profile.get("key_id") and profile["key_id"] != assurance.get("key_id"):
        return False
    if assurance.get("type") == "sigstore":
        return (
            profile.get("certificate_identity") == assurance.get("certificate_identity")
            and profile.get("certificate_oidc_issuer")
            == assurance.get("certificate_oidc_issuer")
        )
    trusted_fingerprint = profile.get("public_key_sha256")
    if isinstance(trusted_fingerprint, str) and trusted_fingerprint:
        return trusted_fingerprint == assurance.get("public_key_sha256")
    reference = profile.get("public_key_ref")
    if isinstance(reference, str) and reference:
        from cryptography.hazmat.primitives import serialization

        public_key = serialization.load_pem_public_key(_resolve_secret(reference).encode())
        public_der = public_key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return hashlib.sha256(public_der).hexdigest() == assurance.get("public_key_sha256")
    return False


def _section_digests(analytics: object, records: dict) -> dict[str, str]:
    digests = {"analytics": hashlib.sha256(canonical_json(analytics)).hexdigest()}
    for category, rows in sorted(records.items()):
        digests[f"records/{category}"] = hashlib.sha256(canonical_json(rows)).hexdigest()
    return digests


def _trust_profile(name: str | None, required: bool) -> dict | None:
    if not name:
        return None
    profile = verification_profiles().get(name)
    if not profile and required:
        raise ValueError("Governance evidence verification profile is not configured")
    return profile


def _profile_configuration(value: str, setting_name: str) -> dict[str, dict]:
    try:
        profiles = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{setting_name} must be valid JSON") from exc
    if not isinstance(profiles, dict) or any(
        not isinstance(name, str) or not isinstance(profile, dict)
        for name, profile in profiles.items()
    ):
        raise ValueError(f"{setting_name} must contain named profile objects")
    return profiles


def _resolve_secret(reference: str) -> str:
    from app.secrets import resolve_secret

    return resolve_secret(reference)


def _cosign_executable() -> str:
    executable = settings.cosign_executable
    if not isinstance(executable, str) or not executable or "\x00" in executable or len(executable) > 1024:
        raise ValueError("ODG_COSIGN_EXECUTABLE is invalid")
    return executable


def _run_cosign(command: list[str], environment: dict[str, str] | None) -> None:
    try:
        completed = subprocess.run(
            command,
            env=environment,
            capture_output=True,
            check=False,
            timeout=settings.cosign_timeout_seconds,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Sigstore signing or verification is unavailable") from exc
    if completed.returncode != 0:
        raise RuntimeError("Sigstore signing or verification failed")


def _encode(value: bytes) -> str:
    return base64.b64encode(value).decode()


def _decode(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.isoformat().replace("+00:00", "Z")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
