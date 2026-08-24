import { api } from "./api";

const CACHE_MS = 30 * 60 * 1000;
const PREFETCH_RETRIES = 3;
const inflight = new Map();

export function sidebarCacheKey(shopId) {
  return `category-sidebar:${shopId}`;
}

export function treeCacheKey(shopId, parent) {
  return `category-tree:${shopId}:${parent}`;
}

function treePayloadValid(data) {
  return Array.isArray(data?.children) && data.children.length > 0;
}

export function readCategoryCache(key) {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.at || Date.now() - parsed.at > CACHE_MS) return null;
    if (key.startsWith("category-sidebar:")) {
      const used = parsed.data?.used || [];
      const recent = parsed.data?.recent || [];
      if (!used.length && !recent.length) return null;
    }
    if (key.startsWith("category-tree:") && !treePayloadValid(parsed.data)) {
      sessionStorage.removeItem(key);
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}

export function writeCategoryCache(key, data) {
  if (key.startsWith("category-tree:") && !treePayloadValid(data)) return;
  try {
    sessionStorage.setItem(key, JSON.stringify({ at: Date.now(), data }));
  } catch {
    /* ignore quota errors */
  }
}

export function invalidateCategoryCache(key) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

async function fetchRootTree(shopId) {
  let lastError = null;
  for (let attempt = 0; attempt < PREFETCH_RETRIES; attempt += 1) {
    try {
      const data = await api.categories(shopId, "0");
      const children = data.children || [];
      if (children.length) {
        return { children, path: data.path || [] };
      }
      lastError = new Error("类目树为空");
    } catch (error) {
      lastError = error;
    }
    if (attempt + 1 < PREFETCH_RETRIES) {
      await new Promise((resolve) => setTimeout(resolve, 180 * (attempt + 1)));
    }
  }
  if (lastError) throw lastError;
  return null;
}

async function runPrefetch(shopId) {
  const sidebarKey = sidebarCacheKey(shopId);
  const treeKey = treeCacheKey(shopId, "0");
  await Promise.allSettled([
    (async () => {
      try {
        const data = await api.categorySidebar(shopId);
        if ((data.used || []).length || (data.recent || []).length) {
          writeCategoryCache(sidebarKey, data);
        }
      } catch {
        /* optional warm-up */
      }
    })(),
    (async () => {
      if (readCategoryCache(treeKey)) return;
      try {
        const tree = await fetchRootTree(shopId);
        if (tree) writeCategoryCache(treeKey, tree);
      } catch {
        invalidateCategoryCache(treeKey);
      }
    })(),
  ]);
}

export function awaitCategoryPrefetch(shopId) {
  if (!shopId) return Promise.resolve();
  return inflight.get(shopId) || Promise.resolve();
}

export function prefetchCategoryPicker(shopId) {
  if (!shopId) return Promise.resolve();
  const existing = inflight.get(shopId);
  if (existing) return existing;
  const job = runPrefetch(shopId).finally(() => {
    if (inflight.get(shopId) === job) inflight.delete(shopId);
  });
  inflight.set(shopId, job);
  return job;
}
