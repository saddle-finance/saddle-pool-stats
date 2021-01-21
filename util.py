import boto3
import botocore
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

FLEEK_ENDPOINT = "https://storageapi.fleek.co"


def get_existing_file_content(fleek_aws_client, obj_bucket, obj_key):
    try:
        obj = fleek_aws_client.get_object(Bucket=obj_bucket, Key=obj_key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except fleek_aws_client.exceptions.NoSuchKey:
        logger.info("No existing file has been found.")
        return []
    except Exception as e:
        logger.error(f"Error reading existing file: {e}")
        return None


def get_fleek_client(key, secret):
    return boto3.client(
        service_name="s3",
        api_version="2006-03-01",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        endpoint_url=FLEEK_ENDPOINT,
        region_name="us-east-1",
        config=botocore.config.Config(s3=dict(addressing_style="path")),
    )
