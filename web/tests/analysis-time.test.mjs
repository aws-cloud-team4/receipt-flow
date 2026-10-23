import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../src/analysisTime.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { analysisSeconds } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`
);

test("queue waiting is excluded from AI processing time", () => {
  assert.equal(analysisSeconds({ timings: {
    uploaded: "2026-10-18T13:40:00Z",
    analysis_started: "2026-10-18T22:50:00+09:00",
    analysis_finished: "2026-10-18T13:50:04Z",
  } }), "4.0");
});

test("legacy receipts without a worker start mark remain readable", () => {
  assert.equal(analysisSeconds({ timings: {
    uploaded: "2026-10-18T13:40:00Z",
    analysis_finished: "2026-10-18T13:40:09Z",
  } }), "9.0");
});

test("unfinished, invalid and reversed timings are not shown as a duration", () => {
  for (const timings of [
    {},
    { analysis_started: "2026-10-18T13:40:00Z" },
    { analysis_started: "invalid", analysis_finished: "2026-10-18T13:40:00Z" },
    { analysis_started: "2026-10-18T13:40:09Z", analysis_finished: "2026-10-18T13:40:00Z" },
  ]) assert.equal(analysisSeconds({ timings }), null);
});
