import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

// Compile the actual pure sorting module with the project's TypeScript dependency.
const source = await readFile(new URL("../src/reviewOrder.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { compareSubmissionTime, orderForReview } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

test("mixed UTC and Korean timestamps follow actual submission order", () => {
  const earlier = { id: "earlier", submitted_at: "2026-10-17T19:41:00+09:00" };
  const later = { id: "later", submitted_at: "2026-10-17T16:42:00Z" };
  const queue = [later, earlier];
  assert.deepEqual(orderForReview(queue, []).map((r) => r.id), ["earlier", "later"]);
  assert.deepEqual(queue.map((r) => r.id), ["later", "earlier"]);
});

test("equal instants and missing legacy timestamps have deterministic comparisons", () => {
  assert.equal(compareSubmissionTime(
    { submitted_at: "2026-10-18T01:00:00+09:00" },
    { submitted_at: "2026-10-17T16:00:00Z" },
  ), 0);
  assert.equal(compareSubmissionTime({ submitted_at: null }, { submitted_at: "invalid" }), 0);
});

test("skipped receipts remain at the back in skip order", () => {
  const queue = [
    { id: "first", submitted_at: "2026-10-17T01:00:00Z" },
    { id: "second", submitted_at: "2026-10-17T02:00:00Z" },
    { id: "third", submitted_at: "2026-10-17T03:00:00Z" },
  ];
  assert.deepEqual(orderForReview(queue, ["second", "first"]).map((r) => r.id), ["third", "second", "first"]);
});
