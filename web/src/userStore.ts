/** Small per-user lists kept in this browser (conveniences only: recents, "later" marks). */
let owner = "";

/** Called once the signed-in user is known. */
export function setStoreOwner(sub: string) {
  owner = sub;
}

export function readList<T>(name: string): T[] {
  if (!owner) return [];
  try {
    const list = JSON.parse(localStorage.getItem(`rf.${name}.${owner}`) ?? "[]");
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function writeList<T>(name: string, list: T[]) {
  if (!owner) return;
  try {
    localStorage.setItem(`rf.${name}.${owner}`, JSON.stringify(list));
  } catch {
    // private window or storage full: these lists are a convenience only
  }
}
