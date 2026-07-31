# AWS S3 Connector

## Authentication and permissions

The connector uses boto3's standard credential chain. Prefer a dedicated workload role restricted to approved buckets and prefixes.

Required actions are `s3:ListBucket` on the bucket and `s3:GetObject` for object metadata. `s3:GetBucketPolicyStatus` enables bucket-level public-access interpretation. No object body is retrieved.

## Collected metadata

Bucket, key, size, provider-modified time, storage class, encryption, ETag, object metadata owner, MIME type, and bucket policy public status.

S3 does not provide a universal object creation or last-access timestamp. OpenDataGraph records those fields as unknown unless another approved source supplies them.

If bucket policy status cannot be read, `public_access` remains false and `metadata.public_access_evidence` is `unknown-insufficient-permission`; this must not be interpreted as proof that the bucket is private.

## Pagination

The connector returns the provider continuation token unchanged as `next_cursor`. Each scan is bounded to one provider page and `max_items`.

## Durable run

```json
{
  "account": "example-bucket",
  "prefix": "approved/",
  "region": "us-east-1",
  "max_items": 500
}
```

Submit the payload to `POST /api/v1/connectors/aws-s3/jobs`. No `secret_ref` is required when the worker has an approved workload role.

Imported and updated counts are recorded in both connector-run and job results. Errors are bounded and never include credentials.
