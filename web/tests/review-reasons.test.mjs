import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../src/reviewReasons.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const {
  MAX_FIELDS, MAX_REASON, PHOTO_REQUESTS, asksRetake, composeRequest, defaultReason, fieldRequest, josa, pointRequest, toggleItem,
} = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

const LABELS = {
  merchant_name: "상호명", transaction_at: "거래 일시", total_amount: "총액", supply_amount: "공급가액",
  vat_amount: "부가세", exempt_amount: "면세금액", business_number: "사업자번호", payment_method: "결제수단",
  card_issuer: "카드사", card_number: "카드번호", approval_number: "승인번호", category: "지출 분류", purpose: "지출 목적",
};
const label = (k) => LABELS[k];
const POINT_CODES = [
  "amount_mismatch", "late_night", "weekend", "duplicate", "same_approval", "unclear_fields", "analysis_failed",
  "edited_fields", "result_unconfirmed", "entertainment", "other_category", "short_purpose",
];

test("review points become requests aimed at the fields they are about", () => {
  assert.deepEqual(pointRequest({ code: "late_night", fields: [] }, label).fields, ["purpose"]);
  const unclear = pointRequest({ code: "unclear_fields", fields: ["merchant_name", "total_amount"] }, label);
  assert.equal(unclear.text, "흐리게 읽힌 상호명, 총액을 사진과 비교해 확인해 주세요.");
  assert.deepEqual(unclear.fields, ["merchant_name", "total_amount"]);
  // reviewer-only points, and field points with no fields, suggest nothing
  assert.equal(pointRequest({ code: "result_unconfirmed", fields: [] }, label), null);
  assert.equal(pointRequest({ code: "analysis_failed", fields: [] }, label), null);
  assert.equal(pointRequest({ code: "edited_fields", fields: [] }, label), null);
  assert.equal(pointRequest({ code: "unknown_code", fields: [] }, label), null);
});

test("field requests quote the submitted value with the right particle", () => {
  assert.equal(fieldRequest("total_amount", "총액", "90,000원").text, "총액(90,000원)을 영수증과 비교해 수정해 주세요.");
  assert.equal(fieldRequest("approval_number", "승인번호", "0123").text, "승인번호(0123)를 영수증과 비교해 수정해 주세요.");
  assert.equal(fieldRequest("business_number", "사업자번호", "—").text, "사업자번호를 영수증을 보고 입력해 주세요.");
  assert.equal(fieldRequest("category", "지출 분류", "기타 업무비").text,
    "지출 분류(기타 업무비)가 지출 목적에 맞는지 확인하고 수정해 주세요.");
  assert.equal(josa("공급가액", "을", "를"), "을");
  assert.equal(josa("카드사", "을", "를"), "를");
});

test("items pick the fields; an empty reason sends their default wording, a written one replaces it", () => {
  const night = pointRequest({ code: "late_night", fields: [] }, label);
  const other = pointRequest({ code: "other_category", fields: ["purpose"] }, label);
  const purpose = fieldRequest("purpose", "지출 목적", "수리");
  const total = fieldRequest("total_amount", "총액", "90,000원");
  let items = toggleItem([], night);
  items = toggleItem(items, other);
  items = toggleItem(items, purpose); // same wording as other_category: sent once
  items = toggleItem(items, total);
  assert.equal(toggleItem(items, night).length, 3);
  const plain = composeRequest(items, "  ");
  assert.equal(plain.reason, defaultReason(items));
  assert.equal(plain.reason.split("\n").length, 3);
  assert.deepEqual(plain.fields, ["purpose", "total_amount"]);
  const written = composeRequest(items, "  총액이 전표와 다르고, 심야 결제 사유가 없어요. ");
  assert.equal(written.reason, "총액이 전표와 다르고, 심야 결제 사유가 없어요.");
  assert.deepEqual(written.fields, plain.fields);
  assert.deepEqual(composeRequest([], " "), { reason: "", fields: [] });
  assert.deepEqual(composeRequest([], "사유만"), { reason: "사유만", fields: [] });
});

test("a retake is flagged so the reviewer is told everything else starts over", () => {
  assert.equal(asksRetake([fieldRequest("merchant_name", "상호명", "가게")]), false);
  assert.equal(asksRetake([PHOTO_REQUESTS[0]]), true);
});

test("picks never target profile fields, and going over the API limits is caught rather than trimmed", () => {
  const all = [
    ...POINT_CODES.map((code) => pointRequest({ code, fields: ["merchant_name", "total_amount"] }, label)).filter(Boolean),
    ...Object.keys(LABELS).map((k) => fieldRequest(k, LABELS[k], "가나다라마바사아자차카타파하 1234567890")),
    ...PHOTO_REQUESTS,
  ];
  const { reason, fields } = composeRequest(all, "");
  assert.ok(!fields.includes("department"));
  assert.ok(fields.includes("photo"));
  // all at once is over the limits: the screen blocks sending instead of trimming silently
  assert.ok(reason.length > MAX_REASON || fields.length > MAX_FIELDS);
  const typical = composeRequest(all.slice(0, 4), "");
  assert.ok(typical.reason.length <= MAX_REASON && typical.fields.length <= MAX_FIELDS);
});
