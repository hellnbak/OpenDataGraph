# Enterprise Demo Mode

Enterprise Demo Mode creates screenshot-ready synthetic organizations that demonstrate OpenDataGraph at realistic scale without connecting to live systems.

## Profiles

| Profile | Organization | Represented assets | Primary story |
|---|---|---:|---|
| `financial-services` | Acme Financial Services | 152,483 | Customer data, lending records, financial controls, long retention periods |
| `healthcare` | Northstar Health Network | 238,944 | Patient information, clinical data, research, privacy controls |
| `saas` | OrbitScale SaaS | 87,420 | Source code, customer telemetry, support content, product analytics |
| `fortune-500` | Contoso Global Industries | 1,248,690 | Multi-cloud sprawl, acquisitions, legacy data, distributed ownership |

All names, domains, files, owners, metrics, findings, and policy decisions are synthetic.

## Weighted records

The demo stores a manageable number of interactive records and assigns each a `represented_count` in `metadata_json`. Dashboard totals aggregate these weights. This makes it possible to demonstrate an estate with more than one million assets using a few hundred local rows.

Weighted totals are appropriate for product demonstrations and UI testing. They are not intended for performance benchmarking.

## Generate from the UI

1. Open `http://localhost:8080`.
2. Select **Enterprise Demo Mode**.
3. Choose an industry profile.
4. Choose 160, 240, or 400 interactive records.
5. Select **Generate environment**.

## Generate through the API

```bash
curl -X POST http://localhost:8080/api/v1/demo/generate \
  -H 'Content-Type: application/json' \
  -d '{"profile":"healthcare","samples":240,"seed":41}'
```

Available profiles:

```bash
curl http://localhost:8080/api/v1/demo/profiles
```

## Recommended screenshots

1. Financial Services overview with catalog size, restricted data, archive candidates, and AI blocked metrics.
2. Risk posture and retention intelligence panels.
3. Source coverage and top priority findings.
4. Restricted asset detail drawer showing classification evidence and lifecycle guidance.
5. AI policy evaluation denying a restricted asset to External AI.
6. Enterprise Demo Mode profile selector.

## Safety

Enterprise Demo Mode never connects to a cloud account. Generating a profile replaces the current local catalog, but it does not alter any external system. The generated records are clearly marked with `synthetic: true`.
