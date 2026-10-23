"""DynamoDB single-table access for receipts, history events and chat messages."""

import uuid
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from . import aws
from .domain import OLD_CODES, duplicate_key, now_iso, run_checks

META = "META"


def _pk(receipt_id: str) -> str:
    return f"RECEIPT#{receipt_id}"


def _plain(value: Any) -> Any:
    """DynamoDB returns Decimal; the API speaks int/float."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _ddb(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _ddb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_ddb(v) for v in value]
    return value


def _public(item: dict[str, Any]) -> dict[str, Any]:
    hidden = {"pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk", "dup_key"}
    out = _plain({k: v for k, v in item.items() if k not in hidden})
    fields = out.get("fields")
    if isinstance(fields, dict) and fields.get("category") in OLD_CODES:
        out["fields"] = {**fields, "category": OLD_CODES[fields["category"]]}  # saved before the revision
    return out


def create_receipt(
    owner_sub: str, owner_name: str, processing: str, owner_profile: dict[str, Any] | None = None
) -> dict[str, Any]:
    """`owner_profile` is a snapshot (employee_no, department, position) taken at creation.
    The department field comes from it and is read-only in the service."""
    receipt_id = uuid.uuid4().hex
    profile = {k: (owner_profile or {}).get(k) for k in ("employee_no", "department", "position")}
    now = now_iso()
    item = {
        "pk": _pk(receipt_id),
        "sk": META,
        "id": receipt_id,
        "owner_sub": owner_sub,
        "owner_name": owner_name,
        "owner_profile": profile,
        "processing": processing,
        "analysis_status": "waiting",
        "review_status": "draft",
        "fields": {"department": profile["department"]} if profile["department"] else {},
        "needs_check": [],
        "ai_filled": [],
        "checks": [],
        "image_key": None,
        "created_at": now,
        "updated_at": now,
        "submitted_at": None,
        "timings": {"created": now},
        "gsi1pk": f"OWNER#{owner_sub}",
        "gsi1sk": now,
        "gsi2pk": "STATUS#draft",
        "gsi2sk": now,
    }
    aws.table().put_item(Item=item)
    add_event(receipt_id, owner_name, "created", None)
    return _public(item)


def get_receipt(receipt_id: str) -> dict[str, Any] | None:
    item = aws.table().get_item(Key={"pk": _pk(receipt_id), "sk": META}).get("Item")
    return _public(item) if item else None


class ConflictError(Exception):
    """The receipt was not in the expected state (another request changed it first)."""


def update_receipt(
    receipt_id: str, expect: dict[str, tuple[str, ...]] | None = None, **changes: Any
) -> dict[str, Any]:
    """Set top-level attributes; `timings` is merged key by key. Keeps GSI keys in sync.

    `expect={"review_status": ("submitted",)}` makes the write conditional (raises ConflictError).
    """
    timings = changes.pop("timings", None) or {}
    changes["updated_at"] = now_iso()
    if "review_status" in changes:
        changes["gsi2pk"] = f"STATUS#{changes['review_status']}"
    changes["gsi2sk"] = changes["updated_at"]

    names: dict[str, str] = {}
    values: dict[str, Any] = {}
    sets: list[str] = []
    for i, (key, value) in enumerate(changes.items()):
        names[f"#a{i}"] = key
        values[f":v{i}"] = _ddb(value)
        sets.append(f"#a{i} = :v{i}")
    if timings:
        names["#t"] = "timings"
        for i, (key, value) in enumerate(timings.items()):
            names[f"#t{i}"] = key
            values[f":t{i}"] = value
            sets.append(f"#t.#t{i} = :t{i}")
    condition = ["attribute_exists(pk)"]
    for i, (key, allowed) in enumerate((expect or {}).items()):
        names[f"#e{i}"] = key
        options = []
        for j, value in enumerate(allowed):
            values[f":e{i}_{j}"] = value
            options.append(f":e{i}_{j}")
        condition.append(f"#e{i} IN ({', '.join(options)})")
    try:
        result = aws.table().update_item(
            Key={"pk": _pk(receipt_id), "sk": META},
            UpdateExpression="SET " + ", ".join(sets),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression=" AND ".join(condition),
            ReturnValues="ALL_NEW",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConflictError(receipt_id) from exc
        raise
    return _public(result["Attributes"])


def apply_fields(
    receipt: dict[str, Any],
    fields: dict[str, Any],
    expect: dict[str, tuple[str, ...]] | None = None,
    **changes: Any,
) -> dict[str, Any]:
    """Merge field values, then recompute duplicate key and automatic checks."""
    merged = {**receipt.get("fields", {}), **fields}
    key = duplicate_key(merged)
    duplicate = find_duplicate(receipt["owner_sub"], key, receipt["id"]) if key else None
    approval = merged.get("approval_number")
    same_approval = find_same_approval(receipt["owner_sub"], approval, receipt["id"]) if approval else None
    return update_receipt(
        receipt["id"],
        expect=expect,
        fields=merged,
        checks=run_checks(merged, duplicate, same_approval),
        dup_key=key,
        **changes,
    )


def find_duplicate(owner_sub: str, key: str, exclude_id: str) -> str | None:
    for item in _query_owner(owner_sub):
        if item.get("dup_key") == key and item["id"] != exclude_id:
            return item["id"]
    return None


def find_same_approval(owner_sub: str, approval: str, exclude_id: str) -> str | None:
    """Same card approval number among this employee's receipts (a near-certain duplicate).

    Across employees this would need an index on approval_number; not done yet.
    """
    for item in _query_owner(owner_sub):
        if item.get("fields", {}).get("approval_number") == approval and item["id"] != exclude_id:
            return item["id"]
    return None


def _query_owner(owner_sub: str) -> list[dict[str, Any]]:
    resp = aws.table().query(
        IndexName="gsi1",
        KeyConditionExpression=Key("gsi1pk").eq(f"OWNER#{owner_sub}"),
        ScanIndexForward=False,
    )
    return resp["Items"]


def list_by_owner(owner_sub: str) -> list[dict[str, Any]]:
    return [_public(i) for i in _query_owner(owner_sub)]


def list_by_status(status: str, limit: int = 200) -> list[dict[str, Any]]:
    resp = aws.table().query(
        IndexName="gsi2",
        KeyConditionExpression=Key("gsi2pk").eq(f"STATUS#{status}"),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [_public(i) for i in resp["Items"]]


def _children(receipt_id: str, prefix: str) -> list[dict[str, Any]]:
    resp = aws.table().query(
        KeyConditionExpression=Key("pk").eq(_pk(receipt_id)) & Key("sk").begins_with(prefix),
    )
    return [_public(i) for i in resp["Items"]]


def delete_receipt(receipt_id: str, expect_status: tuple[str, ...] | None = ("draft",)) -> None:
    """Delete the receipt and everything under it (events, chat). Raises ConflictError if its
    review status is not one of `expect_status` (checked in the same write as the delete);
    `None` deletes in any status (admin)."""
    table = aws.table()
    condition: dict[str, Any] = {"ConditionExpression": "attribute_exists(pk)"}
    if expect_status is not None:
        values = {f":s{i}": v for i, v in enumerate(expect_status)}
        condition = {
            "ConditionExpression": f"attribute_exists(pk) AND #s IN ({', '.join(values)})",
            "ExpressionAttributeNames": {"#s": "review_status"},
            "ExpressionAttributeValues": values,
        }
    try:
        table.delete_item(Key={"pk": _pk(receipt_id), "sk": META}, **condition)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConflictError(receipt_id) from exc
        raise
    query: dict[str, Any] = {
        "KeyConditionExpression": Key("pk").eq(_pk(receipt_id)),
        "ProjectionExpression": "pk, sk",
    }
    with table.batch_writer() as batch:
        while True:
            resp = table.query(**query)
            for item in resp["Items"]:
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            if "LastEvaluatedKey" not in resp:
                break
            query["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def add_event(receipt_id: str, actor: str, action: str, note: str | None) -> None:
    at = now_iso()
    aws.table().put_item(
        Item={
            "pk": _pk(receipt_id),
            "sk": f"EVENT#{at}#{uuid.uuid4().hex[:6]}",
            "at": at,
            "actor": actor,
            "action": action,
            "note": note,
        }
    )


def list_events(receipt_id: str) -> list[dict[str, Any]]:
    return _children(receipt_id, "EVENT#")


def add_message(receipt_id: str, role: str, text: str, **extra: Any) -> dict[str, Any]:
    at = now_iso()
    item = {
        "pk": _pk(receipt_id),
        "sk": f"MSG#{at}#{uuid.uuid4().hex[:6]}",
        "at": at,
        "role": role,
        "text": text,
        **extra,
    }
    aws.table().put_item(Item=_ddb(item))
    return _public(item)


def delete_messages(receipt_id: str) -> int:
    """Remove the whole chat of a receipt (a new photo starts the conversation over)."""
    table = aws.table()
    query: dict[str, Any] = {
        "KeyConditionExpression": Key("pk").eq(_pk(receipt_id)) & Key("sk").begins_with("MSG#"),
        "ProjectionExpression": "pk, sk",
    }
    count = 0
    with table.batch_writer() as batch:
        while True:
            resp = table.query(**query)
            for item in resp["Items"]:
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                count += 1
            if "LastEvaluatedKey" not in resp:
                break
            query["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return count


def list_messages(receipt_id: str) -> list[dict[str, Any]]:
    return _children(receipt_id, "MSG#")


DELETIONS = "DELETIONS"  # one partition: what an admin deleted (the receipt itself is gone)


def log_deletion(receipt: dict[str, Any], deleted_by: str) -> None:
    at = now_iso()
    aws.table().put_item(
        Item=_ddb(
            {
                "pk": DELETIONS,
                "sk": f"{at}#{receipt['id']}",
                "receipt_id": receipt["id"],
                "deleted_at": at,
                "deleted_by": deleted_by,
                "owner_name": receipt.get("owner_name"),
                "merchant_name": (receipt.get("fields") or {}).get("merchant_name"),
                "total_amount": (receipt.get("fields") or {}).get("total_amount"),
                "review_status": receipt.get("review_status"),
            }
        )
    )


def list_deletions(limit: int = 200) -> list[dict[str, Any]]:
    resp = aws.table().query(
        KeyConditionExpression=Key("pk").eq(DELETIONS), ScanIndexForward=False, Limit=limit
    )
    return [
        {"key": item["sk"], **{k: _plain(v) for k, v in item.items() if k not in ("pk", "sk")}}
        for item in resp["Items"]
    ]


def delete_deletion(key: str | None = None) -> int:
    """Remove one deletion record (`key` = its sk) or, with None, all of them. Returns how many."""
    table = aws.table()
    if key is not None:
        resp = table.delete_item(Key={"pk": DELETIONS, "sk": key}, ReturnValues="ALL_OLD")
        return 1 if resp.get("Attributes") else 0
    query: dict[str, Any] = {
        "KeyConditionExpression": Key("pk").eq(DELETIONS),
        "ProjectionExpression": "pk, sk",
    }
    n = 0
    with table.batch_writer() as batch:
        while True:
            resp = table.query(**query)
            for item in resp["Items"]:
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                n += 1
            if "LastEvaluatedKey" not in resp:
                break
            query["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return n


def next_sequence(name: str, floor: int) -> int:
    """Atomically take the next number of a named counter. A new counter starts after `floor`."""
    resp = aws.table().update_item(
        Key={"pk": "COUNTER", "sk": name},
        UpdateExpression="SET n = if_not_exists(n, :floor) + :one",
        ExpressionAttributeValues={":floor": floor, ":one": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(resp["Attributes"]["n"])


def get_usage(day: str) -> dict[str, Any] | None:
    """The landing page's usage snapshot for a day (YYYY-MM-DD), if taken."""
    item = aws.table().get_item(Key={"pk": "USAGE", "sk": f"DAILY#{day}"}).get("Item")
    return _plain(item["snapshot"]) if item else None


def put_usage(day: str, snapshot: dict[str, Any]) -> None:
    aws.table().put_item(Item={"pk": "USAGE", "sk": f"DAILY#{day}", "snapshot": _ddb(snapshot)})
