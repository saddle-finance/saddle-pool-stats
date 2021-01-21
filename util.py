import boto3
import botocore
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

FLEEK_ENDPOINT = "https://storageapi.fleek.co"


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
