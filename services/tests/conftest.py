import os

import boto3
import pytest
from moto import mock_aws

os.environ.update(
    {
        "RF_ENV_FILE": "does-not-exist.env",  # never pick up the developer's real services/.env
        "RF_AUTH_MODE": "dev",
        "RF_AI_MODE": "mock",
        "RF_TABLE": "rf-test",
        "RF_BUCKET": "rf-test-bucket",
        "RF_REGION": "ap-northeast-2",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "ap-northeast-2",
    }
)
os.environ.pop("AWS_PROFILE", None)

EMP = {"Authorization": "Bearer dev:emp-1:employee:kim"}
EMP2 = {"Authorization": "Bearer dev:emp-2:employee:lee"}
REV = {"Authorization": "Bearer dev:rev-1:reviewer:park"}


def create_table(name: str) -> None:
    gsi = lambda n: {  # noqa: E731
        "IndexName": n,
        "KeySchema": [
            {"AttributeName": f"{n}pk", "KeyType": "HASH"},
            {"AttributeName": f"{n}sk", "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }
    boto3.client("dynamodb", region_name="ap-northeast-2").create_table(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[
            {"AttributeName": a, "AttributeType": "S"}
            for a in ("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk")
        ],
        GlobalSecondaryIndexes=[gsi("gsi1"), gsi("gsi2")],
    )


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    with mock_aws():
        from receiptflow_common import aws

        create_table("rf-test")
        boto3.client("s3", region_name="ap-northeast-2").create_bucket(
            Bucket="rf-test-bucket", CreateBucketConfiguration={"LocationConstraint": "ap-northeast-2"}
        )
        url = boto3.client("sqs", region_name="ap-northeast-2").create_queue(QueueName="rf-test")["QueueUrl"]
        monkeypatch.setenv("RF_QUEUE_URL", url)
        aws.reset()
        yield
        aws.reset()


@pytest.fixture
def api():
    from api_service.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture
def pre():
    from fastapi.testclient import TestClient
    from preprocess_service.main import app

    return TestClient(app)


@pytest.fixture
def chat():
    from chat_service.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)
