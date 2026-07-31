import hashlib
import secrets
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    CredentialRotation,
    ServiceAccount,
    ServiceAccountCredential,
    utc_now,
)


PBKDF2_ITERATIONS = 310_000
KEY_PREFIX = "odg_sa"


def create_service_account(
    db: Session,
    tenant_id: str,
    name: str,
    description: str,
    owner: str,
    role: str,
    created_by: str,
    credential_days: int | None = None,
) -> tuple[ServiceAccount, ServiceAccountCredential, str]:
    from app.auth import ROLES

    if role not in ROLES:
        raise ValueError("Service account role is invalid")
    days = credential_days or settings.service_account_credential_days
    if not 1 <= days <= 365:
        raise ValueError("Service account credential lifetime must be 1 to 365 days")
    account = ServiceAccount(
        tenant_id=tenant_id,
        account_id=str(uuid4()),
        name=name,
        description=description,
        owner=owner,
        role=role,
        created_by=created_by,
    )
    db.add(account)
    db.flush()
    credential, key = _issue_credential(db, account, days)
    db.commit()
    db.refresh(account)
    db.refresh(credential)
    return account, credential, key


def authenticate_service_account(db: Session, key: str) -> dict | None:
    parsed = _parse_key(key)
    if not parsed:
        return None
    credential_id, secret = parsed
    credential = db.scalar(
        select(ServiceAccountCredential).where(
            ServiceAccountCredential.credential_id == credential_id,
            ServiceAccountCredential.status == "active",
        )
    )
    if not credential:
        return None
    now = utc_now()
    if credential.expires_at <= now or (
        credential.retire_after is not None and credential.retire_after <= now
    ):
        return None
    expected = _hash_secret(secret, credential.secret_salt)
    if not secrets.compare_digest(expected, credential.secret_hash):
        return None
    account = db.scalar(
        select(ServiceAccount).where(
            ServiceAccount.tenant_id == credential.tenant_id,
            ServiceAccount.account_id == credential.account_id,
            ServiceAccount.status == "active",
        )
    )
    if not account:
        return None
    credential.last_used_at = now
    account.last_authenticated_at = now
    db.commit()
    return {
        "subject": f"service-account:{account.account_id}",
        "role": account.role,
        "tenant_id": account.tenant_id,
        "account_id": account.account_id,
        "credential_id": credential.credential_id,
    }


def rotate_service_account(
    db: Session,
    account: ServiceAccount,
    requested_by: str,
    grace_hours: int | None = None,
    credential_days: int | None = None,
) -> tuple[CredentialRotation, ServiceAccountCredential, str]:
    if account.status != "active":
        raise ValueError("Only active service accounts can rotate credentials")
    active_rotation = db.scalar(
        select(CredentialRotation).where(
            CredentialRotation.tenant_id == account.tenant_id,
            CredentialRotation.account_id == account.account_id,
            CredentialRotation.status == "grace-period",
            CredentialRotation.grace_ends_at > utc_now(),
        )
    )
    if active_rotation:
        raise ValueError("Service account already has an active credential rotation")
    active_credential = db.scalar(
        select(ServiceAccountCredential)
        .where(
            ServiceAccountCredential.tenant_id == account.tenant_id,
            ServiceAccountCredential.account_id == account.account_id,
            ServiceAccountCredential.status == "active",
            ServiceAccountCredential.expires_at > utc_now(),
        )
        .order_by(ServiceAccountCredential.issued_at.desc())
        .limit(1)
    )
    if not active_credential:
        raise ValueError("Service account has no active credential")
    grace = (
        settings.service_account_rotation_grace_hours
        if grace_hours is None
        else grace_hours
    )
    if not 0 <= grace <= 168:
        raise ValueError("Credential rotation grace period must be 0 to 168 hours")
    days = credential_days or settings.service_account_credential_days
    if not 1 <= days <= 365:
        raise ValueError("Service account credential lifetime must be 1 to 365 days")
    credential, key = _issue_credential(db, account, days)
    grace_ends_at = utc_now() + timedelta(hours=grace)
    active_credential.retire_after = grace_ends_at
    if grace == 0:
        active_credential.status = "revoked"
        active_credential.revoked_at = utc_now()
    rotation = CredentialRotation(
        tenant_id=account.tenant_id,
        rotation_id=str(uuid4()),
        account_id=account.account_id,
        old_credential_id=active_credential.credential_id,
        new_credential_id=credential.credential_id,
        status="completed" if grace == 0 else "grace-period",
        grace_ends_at=grace_ends_at,
        requested_by=requested_by,
        completed_at=utc_now() if grace == 0 else None,
    )
    db.add(rotation)
    db.commit()
    db.refresh(rotation)
    db.refresh(credential)
    return rotation, credential, key


def complete_rotation(
    db: Session,
    rotation: CredentialRotation,
) -> CredentialRotation:
    if rotation.status == "completed":
        return rotation
    if rotation.status != "grace-period":
        raise ValueError("Credential rotation is not active")
    old_credential = db.scalar(
        select(ServiceAccountCredential).where(
            ServiceAccountCredential.tenant_id == rotation.tenant_id,
            ServiceAccountCredential.credential_id == rotation.old_credential_id,
        )
    )
    if old_credential:
        old_credential.status = "revoked"
        old_credential.revoked_at = utc_now()
        old_credential.retire_after = utc_now()
    rotation.status = "completed"
    rotation.completed_at = utc_now()
    db.commit()
    db.refresh(rotation)
    return rotation


def disable_service_account(
    db: Session,
    account: ServiceAccount,
) -> ServiceAccount:
    if account.status == "disabled":
        return account
    now = utc_now()
    account.status = "disabled"
    account.disabled_at = now
    credentials = db.scalars(
        select(ServiceAccountCredential).where(
            ServiceAccountCredential.tenant_id == account.tenant_id,
            ServiceAccountCredential.account_id == account.account_id,
            ServiceAccountCredential.status == "active",
        )
    )
    for credential in credentials:
        credential.status = "revoked"
        credential.revoked_at = now
        credential.retire_after = now
    db.commit()
    db.refresh(account)
    return account


def lifecycle_report(db: Session, tenant_id: str) -> dict:
    now = utc_now()
    stale_before = now - timedelta(days=settings.service_account_stale_days)
    expiring_before = now + timedelta(days=14)
    accounts = list(
        db.scalars(
            select(ServiceAccount)
            .where(ServiceAccount.tenant_id == tenant_id)
            .order_by(ServiceAccount.name)
        ).all()
    )
    credentials = list(
        db.scalars(
            select(ServiceAccountCredential).where(
                ServiceAccountCredential.tenant_id == tenant_id
            )
        ).all()
    )
    rotations = list(
        db.scalars(
            select(CredentialRotation).where(
                CredentialRotation.tenant_id == tenant_id,
                CredentialRotation.status == "grace-period",
                CredentialRotation.grace_ends_at > now,
            )
        ).all()
    )
    by_account: dict[str, list[ServiceAccountCredential]] = {}
    for credential in credentials:
        by_account.setdefault(credential.account_id, []).append(credential)
    account_rows = []
    for account in accounts:
        active_credentials = [
            credential
            for credential in by_account.get(account.account_id, [])
            if credential.status == "active" and credential.expires_at > now
            and (
                credential.retire_after is None
                or credential.retire_after > now
            )
        ]
        next_expiry = min(
            (credential.expires_at for credential in active_credentials),
            default=None,
        )
        account_rows.append(
            {
                "account_id": account.account_id,
                "name": account.name,
                "owner": account.owner,
                "role": account.role,
                "status": account.status,
                "last_authenticated_at": account.last_authenticated_at,
                "active_credentials": len(active_credentials),
                "next_credential_expiry": next_expiry,
                "never_used": account.last_authenticated_at is None,
                "stale": (
                    account.last_authenticated_at is not None
                    and account.last_authenticated_at < stale_before
                ),
            }
        )
    return {
        "total_accounts": len(accounts),
        "active_accounts": sum(account.status == "active" for account in accounts),
        "disabled_accounts": sum(account.status == "disabled" for account in accounts),
        "never_used_accounts": sum(row["never_used"] for row in account_rows),
        "stale_accounts": sum(row["stale"] for row in account_rows),
        "active_credentials": sum(
            credential.status == "active" and credential.expires_at > now
            and (
                credential.retire_after is None
                or credential.retire_after > now
            )
            for credential in credentials
        ),
        "expiring_credentials": sum(
            credential.status == "active"
            and now < credential.expires_at <= expiring_before
            and (
                credential.retire_after is None
                or credential.retire_after > now
            )
            for credential in credentials
        ),
        "active_rotations": len(rotations),
        "accounts": account_rows,
    }


def service_account_response(
    account: ServiceAccount,
    credentials: list[ServiceAccountCredential] | None = None,
) -> dict:
    return {
        "account_id": account.account_id,
        "name": account.name,
        "description": account.description,
        "owner": account.owner,
        "role": account.role,
        "status": account.status,
        "last_authenticated_at": account.last_authenticated_at,
        "created_by": account.created_by,
        "created_at": account.created_at,
        "disabled_at": account.disabled_at,
        "credentials": [
            credential_response(credential) for credential in (credentials or [])
        ],
    }


def credential_response(credential: ServiceAccountCredential) -> dict:
    return {
        "credential_id": credential.credential_id,
        "status": credential.status,
        "issued_at": credential.issued_at,
        "expires_at": credential.expires_at,
        "retire_after": credential.retire_after,
        "revoked_at": credential.revoked_at,
        "last_used_at": credential.last_used_at,
    }


def rotation_response(rotation: CredentialRotation) -> dict:
    return {
        "rotation_id": rotation.rotation_id,
        "account_id": rotation.account_id,
        "old_credential_id": rotation.old_credential_id,
        "new_credential_id": rotation.new_credential_id,
        "status": rotation.status,
        "grace_ends_at": rotation.grace_ends_at,
        "requested_by": rotation.requested_by,
        "created_at": rotation.created_at,
        "completed_at": rotation.completed_at,
    }


def _issue_credential(
    db: Session,
    account: ServiceAccount,
    days: int,
) -> tuple[ServiceAccountCredential, str]:
    credential_id = str(uuid4())
    secret = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    credential = ServiceAccountCredential(
        tenant_id=account.tenant_id,
        credential_id=credential_id,
        account_id=account.account_id,
        secret_salt=salt,
        secret_hash=_hash_secret(secret, salt),
        expires_at=utc_now() + timedelta(days=days),
    )
    db.add(credential)
    return credential, f"{KEY_PREFIX}_{credential_id}_{secret}"


def _hash_secret(secret: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        secret.encode(),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()


def _parse_key(key: str) -> tuple[str, str] | None:
    if not isinstance(key, str):
        return None
    parts = key.split("_", 3)
    if len(parts) != 4 or parts[0] != "odg" or parts[1] != "sa":
        return None
    credential_id, secret = parts[2], parts[3]
    if len(credential_id) != 36 or len(secret) < 32:
        return None
    return credential_id, secret
