import { api } from "./api";

const CACHE_MS = 30 * 60 * 1000;

export function sidebarCacheKey(shopId) {
  return `category-sidebar:${shopId}`;
}

export function treeCacheKey(shopId, parent) {
  return `category-tree:${shopId}:${parent}`;
}

export function readCategoryCache(key) {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.at || Date.now() - parsed.at > CACHE_MS) return null;
    return parsed.data;
  } catch {
    return null;
  }
}

export function writeCategoryCache(key, data) {
  try {
    sessionStorage.setItem(key, JSON.stringify({ at: Date.now(), data }));
  } catch {
    /* ignore quota errors */
  }
}

export async function prefetchCategoryPicker(shopId) {
  if (!shopId) return;
  const sidebarKey = sidebarCacheKey(shopId);
  const cached = readCategoryCache(sidebarKey);
  if (!cached) {
    try {
      const data = await api.categorySidebar(shopId);
      writeCategoryCache(sidebarKey, data);
    } catch {
      /* optional warm-up */
    }
  }
  const treeKey = treeCacheKey(shopId, "0");
  const treeCached = readCategoryCache(treeKey);
  if (!treeCached) {
    try {
      const data = await api.categories(shopId, "0");
      writeCategoryCache(treeKey, { children: data.children || [], path: data.path || [] });
    } catch {
      /* optional warm-up */
    }
  }
  void api
    .categorySidebar(shopId, { refresh: true })
    .then((data) => writeCategoryCache(sidebarKey, data))
    .catch(() => {});
}
