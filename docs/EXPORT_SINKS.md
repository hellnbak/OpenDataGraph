# Graph Export Sinks

Asynchronous graph exports use a scheme-based sink adapter registry. Built-in external adapters support `s3://`, `https://`, `gs://`, and `azblob://` destinations. Local and configured S3 storage remain available when no external `sink_uri` is supplied.

## S3 sink

An S3 destination must be a complete `s3://bucket/key` URI. The bucket must appear in `ODG_GRAPH_EXPORT_ALLOWED_SINK_BUCKETS`. Credentials, user information, query parameters, and fragments are rejected.

Workers use the runtime AWS credential chain by default. Set `ODG_GRAPH_EXPORT_S3_EXCHANGE_PROFILE` to use temporary AWS credentials from a named workload exchange profile. Limit write permission to the approved bucket and prefix. The export records destination, SHA-256, size, edge count, and truncation state.

## Google Cloud Storage sink

A Google Cloud Storage destination uses `gs://bucket/key`. The bucket must appear in `ODG_GRAPH_EXPORT_GCS_ALLOWED_SINK_BUCKETS`, and `ODG_GRAPH_EXPORT_GCS_EXCHANGE_PROFILE` must select a Google Cloud workload exchange profile. The worker performs a non-redirecting media upload and sends the SHA-256 as object metadata.

## Azure Blob sink

An Azure destination uses `azblob://account/container/blob`. The exact `account/container` pair must appear in `ODG_GRAPH_EXPORT_AZURE_ALLOWED_SINKS`, and `ODG_GRAPH_EXPORT_AZURE_EXCHANGE_PROFILE` must select an Azure workload exchange profile. Storage account and container syntax is validated before a non-redirecting Block Blob upload.

## HTTPS sink

An HTTPS destination requires:

- an exact host in `ODG_GRAPH_EXPORT_HTTPS_ALLOWED_HOSTS`;
- a mounted short-lived token path in `ODG_GRAPH_EXPORT_HTTPS_IDENTITY_TOKEN_FILE`;
- the token file under an `ODG_SECRET_FILE_ROOTS` path;
- an endpoint that accepts an HTTP `PUT` with the export content type.

Workers send `Authorization: Bearer <token>` and `X-Content-SHA256`. They read the token at execution time, do not persist it, and do not follow redirects. URLs containing credentials, query parameters, or fragments are rejected.

HTTPS sinks are push-only. OpenDataGraph cannot download or delete the remote object. Remote retention, integrity verification, cleanup, and rollback remain the destination operator's responsibility.

## API

- `POST /api/v1/graph/exports` accepts optional `sink_uri`.
- `GET /api/v1/graph/export-sinks` reports enabled adapter schemes and configuration presence without exposing identities or token paths.
- Export responses include `retrievable`; it is false for external push sinks.

Keep sink allowlists narrow, isolate worker egress, use destination-specific audiences, and review remote retention before enabling a sink. See [Cloud workload identity exchange](WORKLOAD_EXCHANGE.md).
