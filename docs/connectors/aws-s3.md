# AWS S3 Connector

## Authentication

Uses boto3's standard credential chain: environment variables, profiles, container roles, or instance roles. Prefer a dedicated read-only role.

## Minimum scope

Grant only the target buckets and prefixes. The connector needs bucket listing and object metadata access. It does not download object bodies in v1.1.

## Collected metadata

Bucket, key, size, modified time, storage class, encryption metadata where available, tags, ETag, ownership context, and source account.

## Run

```bash
curl -X POST http://localhost:8080/api/v1/connectors/s3/scan \
 -H 'Content-Type: application/json' \
 -d '{"bucket":"example-bucket","prefix":"","region":"us-east-1","max_objects":500}'
```

## Limitation

S3 does not provide a universally reliable native last-accessed timestamp per object. OpenDataGraph distinguishes known, observed, and derived lifecycle evidence.
