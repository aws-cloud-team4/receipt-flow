"""Consume S3 `incoming/{id}.jpg` events from SQS and store extracted fields."""

import json
import logging
import signal
import time
from typing import Any
from urllib.parse import unquote_plus

from botocore.exceptions import ClientError
from receiptflow_common import aws, store
from receiptflow_common.bedrock import ModelError
from receiptflow_common.config import get_settings
from receiptflow_common.domain import now_iso

from .extractor import PROMPT_VERSION, NotAReceipt, extract

log = logging.getLogger("ocr-worker")
MAX_ATTEMPTS = 3
_running = True


def receipt_ids(body: dict[str, Any]) -> list[tuple[str, str]]:
    """S3 event notification → [(receipt_id, key)]. Test events and other prefixes are ignored."""
    out = []
    for record in body.get("Records", []):
        key = unquote_plus(record.get("s3", {}).get("object", {}).get("key", ""))
        if key.startswith("incoming/") and key.endswith(".jpg"):
            out.append((key.removeprefix("incoming/").removesuffix(".jpg"), key))
    return out


def process(receipt_id: str, key: str, attempt: int = 1) -> bool:
    """Analyse one image. Returns True when the message can be deleted."""
    receipt = store.get_receipt(receipt_id)
    if not receipt:
        log.warning("receipt %s not found for %s", receipt_id, key)
        return True
    if receipt.get("seed"):
        # Fake test data (scripts/seed_dev_data.py) is stored already "read"; its photos still land in
        # incoming/ and reach the queue. Never call the model for them or overwrite what was seeded.
        log.info("receipt %s is seeded test data; skipping %s", receipt_id, key)
        return True
    started = now_iso()
    store.update_receipt(receipt_id, analysis_status="processing", timings={"analysis_started": started})
    try:
        obj = aws.client("s3").get_object(Bucket=get_settings().bucket, Key=key)
        image = obj["Body"].read()
        fields, needs_check, usage, context = extract(image)
    except NotAReceipt as exc:
        _fail(receipt_id, str(exc))
        return True
    except (ModelError, ValueError, json.JSONDecodeError) as exc:
        log.exception("extraction failed for %s", receipt_id)
        _fail(receipt_id, f"분석에 실패했습니다: {exc}")
        return True
    except ClientError:
        log.exception("AWS error for %s (attempt %d)", receipt_id, attempt)
        if attempt >= MAX_ATTEMPTS:
            _fail(receipt_id, "AI 분석 서비스에 일시적인 문제가 있습니다. 다시 시도해 주세요.")
            return True
        store.update_receipt(receipt_id, analysis_status="queued")
        return False

    # Fresh read: the employee may have typed values while the model was working. Theirs win.
    current = store.get_receipt(receipt_id) or receipt
    typed = current.get("fields", {})
    fill = {k: v for k, v in fields.items() if typed.get(k) in (None, "")}
    store.apply_fields(
        current,
        fill,
        analysis_status="done",
        analysis_error=None,
        needs_check=[k for k in needs_check if k in fill],
        # Fields the model filled and nobody has touched yet (the web marks them "AI").
        ai_filled=sorted(set(current.get("ai_filled", [])) | {k for k, v in fill.items() if v is not None}),
        image_key=key,
        ai_context=context,
        result_confirmed_at=None,  # a new reading has to be confirmed again
        model_usage={**usage, "prompt": PROMPT_VERSION, "image_bytes": len(image)},
        timings={"analysis_finished": now_iso()},
    )
    log.info(
        "receipt %s analysed in %sms (%s tokens in)", receipt_id, usage["latency_ms"], usage["input_tokens"]
    )
    return True


def _fail(receipt_id: str, message: str) -> None:
    store.update_receipt(
        receipt_id, analysis_status="failed", analysis_error=message, timings={"analysis_finished": now_iso()}
    )


def poll_once(wait: int = 20) -> int:
    sqs = aws.client("sqs")
    resp = sqs.receive_message(
        QueueUrl=get_settings().queue_url,
        MaxNumberOfMessages=5,
        WaitTimeSeconds=wait,
        MessageSystemAttributeNames=["ApproximateReceiveCount"],
    )
    messages = resp.get("Messages", [])
    for msg in messages:
        attempt = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
        done = True
        try:
            for receipt_id, key in receipt_ids(json.loads(msg["Body"])):
                done = process(receipt_id, key, attempt) and done
        except store.ConflictError:
            log.info("receipt deleted while it was being read; dropping message %s", msg["MessageId"])
        except Exception:
            log.exception("unexpected error handling message %s", msg["MessageId"])
            done = attempt >= MAX_ATTEMPTS
        if done:
            sqs.delete_message(QueueUrl=get_settings().queue_url, ReceiptHandle=msg["ReceiptHandle"])
    return len(messages)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    def stop(*_: Any) -> None:
        global _running
        _running = False
        log.info("stopping after current batch")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    s = get_settings()
    log.info("ocr-worker started (ai_mode=%s, model=%s)", s.ai_mode, s.extract_model)
    while _running:
        try:
            poll_once()
        except Exception:
            log.exception("poll failed")
            time.sleep(5)


if __name__ == "__main__":
    main()
