"""Remove what the developer-login test accounts made: receipts of owner_sub dev-* with their
history, chat and photos. Real accounts' data is left alone.

uv run python scripts/clear_dev_data.py
"""

from boto3.dynamodb.conditions import Attr
from receiptflow_common import aws, store
from receiptflow_common.config import get_settings


def main() -> None:
    table = aws.table()
    scan = {
        "FilterExpression": Attr("sk").eq("META") & Attr("owner_sub").begins_with("dev-"),
        "ProjectionExpression": "id",
    }
    ids: list[str] = []
    while True:
        resp = table.scan(**scan)
        ids += [i["id"] for i in resp["Items"]]
        if "LastEvaluatedKey" not in resp:
            break
        scan["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    s3, bucket = aws.client("s3"), get_settings().bucket
    for rid in ids:
        store.delete_receipt(rid, expect_status=None)
        s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": f"{p}/{rid}.jpg"} for p in ("raw", "incoming")], "Quiet": True},
        )
    print("removed test receipts:", len(ids))


if __name__ == "__main__":
    main()
