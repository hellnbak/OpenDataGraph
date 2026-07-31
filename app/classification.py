import json
import re
from dataclasses import dataclass

from .config import settings


@dataclass
class Classification:
    sensitivity: str
    labels: list[str]
    business_domain: str
    reason: str
    confidence: float
    review_required: bool = False


PATTERNS = {
    "Secrets": [r"api[_-]?key", r"secret", r"password", r"private[_-]?key", r"token", r"-----begin (?:rsa |ec )?private key-----", r"(?i)aws_secret_access_key\s*="],
    "PII": [r"ssn", r"social.?security", r"passport", r"driver.?license", r"date.?of.?birth", r"dob", r"customer[_ -]?export", r"\b\d{3}-\d{2}-\d{4}\b"],
    "Financial": [r"credit.?card", r"bank.?account", r"routing.?number", r"invoice", r"payroll", r"\b(?:\d[ -]*?){13,19}\b"],
    "Health": [r"patient", r"diagnosis", r"medical", r"hipaa", r"prescription"],
    "Source Code": [r"\.py(?:\s|$)", r"\.go(?:\s|$)", r"\.js(?:\s|$)", r"\.ts(?:\s|$)", r"\.java(?:\s|$)", r"\.tf(?:\s|$)", r"\.yaml(?:\s|$)", r"\.yml(?:\s|$)"],
    "Legal": [r"contract", r"nda", r"litigation", r"legal.?hold"],
}

DOMAINS = {
    "HR": ["employee", "candidate", "resume", "payroll", "benefits", "performance"],
    "Finance": ["invoice", "budget", "revenue", "forecast", "tax", "bank"],
    "Engineering": ["source", "repository", "architecture", "api", "terraform", "code"],
    "Legal": ["contract", "nda", "legal", "litigation", "counsel"],
    "Customer": ["customer", "client", "account", "support", "tenant"],
    "Security": ["incident", "vulnerability", "secret", "threat", "security"],
}


def heuristic_classify(name: str, path: str, mime_type: str = "", sample: str = "") -> Classification:
    haystack = f"{name} {path} {mime_type} {sample[:5000]}".lower()
    labels: list[str] = []
    matched: list[str] = []
    for label, patterns in PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, haystack, re.IGNORECASE):
                labels.append(label)
                matched.append(pattern.replace("\\", ""))
                break

    business_domain = "General"
    for domain, keywords in DOMAINS.items():
        if any(keyword in haystack for keyword in keywords):
            business_domain = domain
            break

    if "Secrets" in labels or "Health" in labels or "PII" in labels or ("Financial" in labels and business_domain == "HR"):
        sensitivity = "Restricted"
        confidence = 0.91
    elif "Financial" in labels or "Legal" in labels or "Source Code" in labels:
        sensitivity = "Confidential"
        confidence = 0.82
    elif labels:
        sensitivity = "Internal"
        confidence = 0.72
    else:
        sensitivity = "Internal"
        confidence = 0.55
        labels = ["Business Data"]

    reason = (
        f"Matched metadata indicators: {', '.join(matched[:4])}. Assigned to {business_domain}."
        if matched
        else "No high-risk indicators found in available metadata; defaulted to internal business data."
    )
    return Classification(sensitivity, sorted(set(labels)), business_domain, reason, confidence, confidence < 0.70)


async def ollama_classify(name: str, path: str, mime_type: str, sample: str = "") -> Classification | None:
    import httpx

    prompt = f"""Classify this enterprise data asset. Return ONLY JSON with keys sensitivity, labels, business_domain, reason, confidence.
Sensitivity must be one of Public, Internal, Confidential, Restricted.
Asset name: {name}
Path: {path}
MIME type: {mime_type}
Sample: {sample[:2500]}
"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.ollama_url.rstrip('/')}/api/generate",
                json={"model": settings.ollama_model, "prompt": prompt, "stream": False, "format": "json"},
            )
            response.raise_for_status()
            parsed = json.loads(response.json()["response"])
            return Classification(
                sensitivity=parsed["sensitivity"],
                labels=list(parsed.get("labels", [])),
                business_domain=parsed.get("business_domain", "General"),
                reason=parsed.get("reason", "Classified by local model"),
                confidence=float(parsed.get("confidence", 0.75)),
                review_required=float(parsed.get("confidence", 0.75)) < 0.70,
            )
    except Exception:
        return None


async def classify(name: str, path: str, mime_type: str = "", sample: str = "") -> Classification:
    baseline = heuristic_classify(name, path, mime_type, sample)
    if settings.classification_mode in {"ollama", "hybrid"}:
        model_result = await ollama_classify(name, path, mime_type, sample)
        if model_result:
            return model_result
    return baseline
