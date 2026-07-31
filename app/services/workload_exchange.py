import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.secrets import resolve_secret


PROVIDERS = {"aws", "azure", "gcp"}


@dataclass(repr=False)
class TemporaryCredential:
    provider: str
    expires_at: datetime
    access_token: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    session_token: str | None = None
    subject: str | None = None


def workload_exchange_profiles() -> dict[str, dict]:
    try:
        profiles = json.loads(settings.workload_exchange_profiles_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("ODG_WORKLOAD_EXCHANGE_PROFILES_JSON must be valid JSON") from exc
    if not isinstance(profiles, dict) or any(
        not isinstance(name, str) or not isinstance(profile, dict)
        for name, profile in profiles.items()
    ):
        raise ValueError("ODG_WORKLOAD_EXCHANGE_PROFILES_JSON must contain profile objects")
    return profiles


def workload_exchange_configuration() -> dict:
    return {
        "profiles": [
            {
                "name": name,
                "provider": profile.get("provider"),
                "audience": profile.get("audience"),
                "max_token_seconds": profile.get("max_token_seconds", 3600),
            }
            for name, profile in sorted(workload_exchange_profiles().items())
        ],
        "tokens_persisted": False,
    }


def exchange_workload_identity(profile_name: str) -> TemporaryCredential:
    profile = _validated_profile(profile_name)
    subject_token = resolve_secret(profile["subject_token_ref"])
    provider = profile["provider"]
    if provider == "aws":
        credential = _exchange_aws(profile, subject_token)
    elif provider == "azure":
        credential = _exchange_azure(profile, subject_token)
    else:
        credential = _exchange_gcp(profile, subject_token)
    _validate_credential_lifetime(credential, profile["max_token_seconds"])
    return credential


def test_workload_exchange(profile_name: str) -> dict:
    credential = exchange_workload_identity(profile_name)
    return {
        "profile": profile_name,
        "provider": credential.provider,
        "expires_at": credential.expires_at,
        "subject": credential.subject,
        "temporary": True,
        "credentials_returned": False,
    }


def boto_credentials(profile_name: str) -> dict[str, str]:
    credential = exchange_workload_identity(profile_name)
    if credential.provider != "aws" or not all(
        (
            credential.access_key_id,
            credential.secret_access_key,
            credential.session_token,
        )
    ):
        raise ValueError("Workload exchange profile did not return AWS credentials")
    return {
        "aws_access_key_id": credential.access_key_id,
        "aws_secret_access_key": credential.secret_access_key,
        "aws_session_token": credential.session_token,
    }


def bearer_token(profile_name: str, provider: str) -> str:
    credential = exchange_workload_identity(profile_name)
    if credential.provider != provider or not credential.access_token:
        raise ValueError(f"Workload exchange profile did not return a {provider} bearer token")
    return credential.access_token


def _validated_profile(profile_name: str) -> dict:
    if not isinstance(profile_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", profile_name):
        raise ValueError("Workload exchange profile name is invalid")
    profile = workload_exchange_profiles().get(profile_name)
    if not profile:
        raise ValueError("Workload exchange profile is not configured")
    provider = profile.get("provider")
    subject_token_ref = profile.get("subject_token_ref")
    audience = profile.get("audience")
    maximum = profile.get("max_token_seconds", 3600)
    if provider not in PROVIDERS:
        raise ValueError("Workload exchange provider is unsupported")
    if not isinstance(subject_token_ref, str) or not subject_token_ref.startswith(("env:", "file:")):
        raise ValueError("Workload exchange profiles require subject_token_ref")
    if not isinstance(audience, str) or not audience or len(audience) > 2048:
        raise ValueError("Workload exchange profile audience is invalid")
    if not isinstance(maximum, int) or not 60 <= maximum <= 3600:
        raise ValueError("Workload exchange maximum token lifetime must be 60 to 3600 seconds")
    validated = {**profile, "max_token_seconds": maximum}
    if provider == "aws":
        if maximum < 900:
            raise ValueError(
                "AWS workload exchange maximum token lifetime must be 900 to 3600 seconds"
            )
        role_arn = profile.get("role_arn")
        if not isinstance(role_arn, str) or not re.fullmatch(
            r"arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/[A-Za-z0-9+=,.@_/-]{1,512}",
            role_arn,
        ):
            raise ValueError("AWS workload exchange role_arn is invalid")
    elif provider == "azure":
        tenant_id = profile.get("tenant_id")
        client_id = profile.get("client_id")
        scope = profile.get("scope", "https://storage.azure.com/.default")
        if not isinstance(tenant_id, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,120}", tenant_id):
            raise ValueError("Azure workload exchange tenant_id is invalid")
        if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,120}", client_id):
            raise ValueError("Azure workload exchange client_id is invalid")
        if not isinstance(scope, str) or not scope or len(scope) > 1024:
            raise ValueError("Azure workload exchange scope is invalid")
        validated["scope"] = scope
    else:
        scope = profile.get("scope", "https://www.googleapis.com/auth/cloud-platform")
        if not isinstance(scope, str) or not scope or len(scope) > 1024:
            raise ValueError("Google workload exchange scope is invalid")
        validated["scope"] = scope
    return validated


def _exchange_aws(profile: dict, subject_token: str) -> TemporaryCredential:
    import boto3

    kwargs = {}
    if profile.get("region"):
        kwargs["region_name"] = profile["region"]
    client = boto3.client("sts", **kwargs)
    session_name = profile.get("session_name", "opendatagraph-export")
    if not isinstance(session_name, str) or not re.fullmatch(r"[A-Za-z0-9+=,.@_-]{2,64}", session_name):
        raise ValueError("AWS workload exchange session_name is invalid")
    try:
        response = client.assume_role_with_web_identity(
            RoleArn=profile["role_arn"],
            RoleSessionName=session_name,
            WebIdentityToken=subject_token,
            DurationSeconds=profile["max_token_seconds"],
        )
        credentials = response["Credentials"]
        expiration = credentials["Expiration"]
        if expiration.tzinfo is None:
            expiration = expiration.replace(tzinfo=UTC)
        return TemporaryCredential(
            provider="aws",
            expires_at=expiration.astimezone(UTC),
            access_key_id=credentials["AccessKeyId"],
            secret_access_key=credentials["SecretAccessKey"],
            session_token=credentials["SessionToken"],
            subject=response.get("SubjectFromWebIdentity"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("AWS workload identity exchange returned an invalid response") from exc
    except Exception as exc:
        raise RuntimeError("AWS workload identity exchange failed") from exc


def _exchange_azure(profile: dict, subject_token: str) -> TemporaryCredential:
    import httpx

    url = f"https://login.microsoftonline.com/{profile['tenant_id']}/oauth2/v2.0/token"
    form = {
        "client_id": profile["client_id"],
        "scope": profile["scope"],
        "client_assertion": subject_token,
        "grant_type": "client_credentials",
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
    }
    payload = _token_response(httpx, url, form, "Azure")
    return TemporaryCredential(
        provider="azure",
        expires_at=datetime.now(UTC) + timedelta(seconds=payload["expires_in"]),
        access_token=payload["access_token"],
    )


def _exchange_gcp(profile: dict, subject_token: str) -> TemporaryCredential:
    import httpx

    form = {
        "audience": profile["audience"],
        "grantType": "urn:ietf:params:oauth:grant-type:token-exchange",
        "requestedTokenType": "urn:ietf:params:oauth:token-type:access_token",
        "scope": profile["scope"],
        "subjectToken": subject_token,
        "subjectTokenType": "urn:ietf:params:oauth:token-type:jwt",
    }
    payload = _token_response(httpx, "https://sts.googleapis.com/v1/token", form, "Google")
    return TemporaryCredential(
        provider="gcp",
        expires_at=datetime.now(UTC) + timedelta(seconds=payload["expires_in"]),
        access_token=payload["access_token"],
    )


def _token_response(httpx, url: str, form: dict, provider: str) -> dict:
    try:
        response = httpx.post(
            url,
            data=form,
            headers={"Accept": "application/json"},
            timeout=settings.workload_exchange_http_timeout_seconds,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 32_768
            or not isinstance(expires_in, int)
            or expires_in <= 0
        ):
            raise ValueError("invalid token response")
        return {"access_token": token, "expires_in": expires_in}
    except Exception as exc:
        raise RuntimeError(f"{provider} workload identity exchange failed") from exc


def _validate_credential_lifetime(credential: TemporaryCredential, maximum: int) -> None:
    now = datetime.now(UTC)
    if credential.expires_at <= now or credential.expires_at > now + timedelta(seconds=maximum + 30):
        raise RuntimeError("Workload identity exchange returned an invalid credential lifetime")
