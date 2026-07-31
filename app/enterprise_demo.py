from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class DemoProfile:
    key: str
    name: str
    industry: str
    employees: int
    represented_assets: int
    annual_storage_cost: int
    description: str
    sources: tuple[tuple[str, str, float], ...]
    domains: tuple[str, ...]
    risk_bias: float


PROFILES = {
    "financial-services": DemoProfile(
        key="financial-services", name="Acme Financial Services", industry="Financial Services",
        employees=4200, represented_assets=152483, annual_storage_cost=486000,
        description="Regulated financial data, customer exports, lending records, engineering IP, and long retention periods.",
        sources=(("aws-s3", "prod-data-platform", .25), ("microsoft-365", "acme.onmicrosoft.com", .24),
                 ("google-drive", "acme.example", .13), ("snowflake", "analytics-prod", .15),
                 ("github", "acme-platform", .09), ("postgres", "customer-prod", .08),
                 ("azure-blob", "archive-prod", .06)),
        domains=("Finance", "Customer Data", "Risk", "Legal", "HR", "Engineering", "Sales"), risk_bias=.78,
    ),
    "healthcare": DemoProfile(
        key="healthcare", name="Northstar Health Network", industry="Healthcare",
        employees=7800, represented_assets=238944, annual_storage_cost=720000,
        description="Clinical operations, patient data, research, insurance records, and strict privacy requirements.",
        sources=(("microsoft-365", "northstar.onmicrosoft.com", .28), ("azure-blob", "clinical-archive", .22),
                 ("aws-s3", "research-data", .16), ("snowflake", "health-analytics", .13),
                 ("google-drive", "northstar.example", .08), ("postgres", "patient-services", .08),
                 ("github", "digital-health", .05)),
        domains=("Clinical", "Patient Data", "Research", "Legal", "HR", "Finance", "Engineering"), risk_bias=.9,
    ),
    "saas": DemoProfile(
        key="saas", name="OrbitScale SaaS", industry="B2B SaaS",
        employees=1650, represented_assets=87420, annual_storage_cost=271000,
        description="Cloud-native product data, source code, customer telemetry, support content, and go-to-market systems.",
        sources=(("aws-s3", "orbitscale-prod", .24), ("google-drive", "orbitscale.example", .20),
                 ("github", "orbitscale", .18), ("snowflake", "product-analytics", .14),
                 ("microsoft-365", "orbitscale.onmicrosoft.com", .10), ("postgres", "app-prod", .09),
                 ("azure-blob", "customer-exports", .05)),
        domains=("Engineering", "Product", "Customer Data", "Support", "Sales", "Finance", "HR"), risk_bias=.62,
    ),
    "fortune-500": DemoProfile(
        key="fortune-500", name="Contoso Global Industries", industry="Diversified Enterprise",
        employees=62000, represented_assets=1248690, annual_storage_cost=3840000,
        description="A global multi-cloud estate with business-unit sprawl, legacy data, acquisitions, and complex ownership.",
        sources=(("microsoft-365", "contoso.onmicrosoft.com", .25), ("aws-s3", "global-data-lake", .18),
                 ("azure-blob", "enterprise-archive", .17), ("google-drive", "subsidiaries.contoso.example", .09),
                 ("snowflake", "enterprise-analytics", .12), ("github", "contoso-engineering", .08),
                 ("postgres", "business-apps", .06), ("gitlab", "internal-platform", .05)),
        domains=("Engineering", "Operations", "Finance", "Legal", "HR", "Customer Data", "Manufacturing", "Sales"), risk_bias=.82,
    ),
}

TEMPLATES = {
    "Finance": ["FY{year}_board_forecast.xlsx", "payment_reconciliation_{n}.csv", "tax_workpapers_{year}.xlsx", "wire_transfer_audit_{n}.json"],
    "Customer Data": ["customer_export_{year}_{n}.csv", "account_profiles_{n}.parquet", "support_case_archive_{year}.zip", "kyc_records_{n}.json"],
    "Risk": ["credit_risk_model_{n}.pkl", "fraud_investigation_{n}.docx", "model_validation_{year}.pdf"],
    "Legal": ["vendor_msa_{n}.docx", "legal_hold_manifest_{n}.csv", "nda_final_{n}.pdf"],
    "HR": ["employee_payroll_{year}.xlsx", "candidate_background_checks_{n}.pdf", "benefits_enrollment_{year}.csv"],
    "Engineering": ["production.env", "architecture_decision_{n}.md", "service_backup_{year}.tar.gz", "terraform_state_{n}.json"],
    "Sales": ["enterprise_pipeline_{year}.xlsx", "customer_pricing_{n}.pdf", "renewal_forecast_{n}.csv"],
    "Clinical": ["clinical_notes_batch_{n}.json", "care_plan_export_{n}.csv", "diagnostic_results_{year}_{n}.parquet"],
    "Patient Data": ["patient_demographics_{n}.csv", "claims_extract_{year}_{n}.json", "appointment_history_{n}.parquet"],
    "Research": ["trial_dataset_{n}.parquet", "genomics_batch_{n}.vcf", "study_protocol_{n}.pdf"],
    "Product": ["product_roadmap_{year}.pptx", "feature_usage_{n}.parquet", "customer_feedback_{n}.json"],
    "Support": ["support_transcripts_{year}_{n}.json", "escalation_export_{n}.csv", "knowledge_base_{n}.html"],
    "Operations": ["facility_access_log_{n}.csv", "supplier_master_{n}.xlsx", "operations_runbook_{n}.docx"],
    "Manufacturing": ["plant_telemetry_{n}.parquet", "quality_incidents_{n}.csv", "design_specification_{n}.pdf"],
}

EXT_MIME = {
    "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf", "parquet": "application/octet-stream", "pkl": "application/octet-stream",
    "md": "text/markdown", "env": "text/plain", "zip": "application/zip", "gz": "application/gzip",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation", "html": "text/html",
    "vcf": "text/plain",
}


def profile_catalog() -> list[dict]:
    return [{"key": p.key, "name": p.name, "industry": p.industry, "employees": p.employees,
             "represented_assets": p.represented_assets, "description": p.description} for p in PROFILES.values()]


def generate_enterprise_assets(profile_key: str, samples: int = 240, seed: int = 41) -> tuple[DemoProfile, list[dict]]:
    if profile_key not in PROFILES:
        raise KeyError(profile_key)
    profile = PROFILES[profile_key]
    samples = max(80, min(samples, 600))
    rng = random.Random(f"{profile_key}:{seed}:{samples}")
    now = datetime.now(UTC).replace(tzinfo=None)
    source_names, source_accounts, source_weights = zip(*profile.sources)
    base_weight, remainder = divmod(profile.represented_assets, samples)
    records = []

    for i in range(samples):
        domain = rng.choice(profile.domains)
        template = rng.choice(TEMPLATES.get(domain, TEMPLATES["Engineering"]))
        year = rng.randint(2017, now.year)
        name = template.format(year=year, n=f"{i+1:04d}")
        source = rng.choices(source_names, weights=source_weights, k=1)[0]
        account = dict((s, a) for s, a, _ in profile.sources)[source]
        age_days = rng.randint(10, 3300)
        created = now - timedelta(days=age_days)
        modified = created + timedelta(days=rng.randint(0, max(1, age_days)))
        inactivity = int(rng.triangular(0, min(age_days, 1400), min(age_days, 850)))
        last_access = now - timedelta(days=inactivity)
        ext = name.rsplit(".", 1)[-1]
        represented = base_weight + (1 if i < remainder else 0)
        public = rng.random() < (.012 if profile.risk_bias < .75 else .024)
        size = int(10 ** rng.uniform(3.7, 9.2))
        owner_team = domain.lower().replace(" ", "-")
        metadata = {
            "demo_profile": profile.key,
            "represented_count": represented,
            "annual_storage_cost_share": round(profile.annual_storage_cost * represented / profile.represented_assets, 2),
            "synthetic": True,
            "department": domain,
            "region": rng.choice(["us-east-1", "us-west-2", "eu-west-1", "central-us"]),
        }
        records.append({
            "source": source, "source_account": account,
            "external_id": f"demo://{profile.key}/{source}/{i:05d}/{name}", "name": name,
            "path": f"{domain}/{year}/{name}", "mime_type": EXT_MIME.get(ext, "application/octet-stream"),
            "size_bytes": size, "owner": f"{owner_team}@{profile.key}.example",
            "created_at": created, "modified_at": modified, "last_accessed_at": last_access,
            "encryption": rng.choice(["Provider managed", "KMS customer key", "AES256"]),
            "public_access": public, "metadata_json": json.dumps(metadata),
        })
    return profile, records


def represented_count(asset) -> int:
    try:
        return max(1, int(json.loads(asset.metadata_json or "{}").get("represented_count", 1)))
    except (TypeError, ValueError, json.JSONDecodeError):
        return 1
