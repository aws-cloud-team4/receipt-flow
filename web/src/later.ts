import type { Receipt } from "./api";
import { readList, writeList } from "./userStore";
import { orderForReview } from "./reviewOrder";

/** Submitted receipts a reviewer skipped with "건너뛰기". Kept in this browser, per reviewer. */
export const laterIds = () => new Set(readList<string>("later"));

/** Kept in skip order: skipping again moves it to the very back. */
const laterList = () => readList<string>("later");

export function markLater(id: string) {
  writeList("later", [...laterList().filter((v) => v !== id), id]);
}

export function clearLater(id: string) {
  writeList("later", [...laterIds()].filter((v) => v !== id));
}

/** Review order: first in, first out, with the ones put off at the end in the order they were put off,
 * so skipping keeps going round every receipt instead of bouncing between the two oldest. */
export function reviewOrder(queue: Receipt[]): Receipt[] {
  return orderForReview(queue, laterList());
}
