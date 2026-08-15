"""
Generic S3-compatible storage wrapper. Points at MinIO locally via S3_ENDPOINT.
Moving to production later (Cloudflare R2 / AWS S3) is a config change only —
this code never changes, only the env vars in .env do.
"""

import boto3
from botocore.client import Config as BotoConfig

from app.core.config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=BotoConfig(signature_version="s3v4"),
    )


def ensure_buckets():
    client = get_s3_client()
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    for bucket in [settings.s3_bucket_kb_permanent, settings.s3_bucket_staging]:
        if bucket not in existing:
            client.create_bucket(Bucket=bucket)


def put_object(bucket: str, key: str, file_bytes: bytes):
    client = get_s3_client()
    client.put_object(Bucket=bucket, Key=key, Body=file_bytes)


def get_object(bucket: str, key: str) -> bytes:
    client = get_s3_client()
    resp = client.get_object(Bucket=bucket, Key=key)
    return resp["Body"].read()


def delete_object(bucket: str, key: str):
    client = get_s3_client()
    client.delete_object(Bucket=bucket, Key=key)


def copy_object(src_bucket: str, src_key: str, dst_bucket: str, dst_key: str):
    client = get_s3_client()
    client.copy_object(Bucket=dst_bucket, CopySource={"Bucket": src_bucket, "Key": src_key}, Key=dst_key)
