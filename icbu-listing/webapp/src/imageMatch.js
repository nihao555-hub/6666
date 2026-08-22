/** Match co-uploaded images to spreadsheet SKUs without forcing exact renames. */

function normalizeSku(sku) {
  return String(sku || "").trim().toLowerCase();
}

function normalizePath(name) {
  return String(name || "").replace(/\\/g, "/").toLowerCase();
}

function stemOf(pathOrName) {
  const base = pathOrName.split("/").pop() || pathOrName;
  const dot = base.lastIndexOf(".");
  return dot >= 0 ? base.slice(0, dot) : base;
}

function fileMatchesSku(pathOrName, skuNorm) {
  if (!skuNorm) return false;
  const path = normalizePath(pathOrName);
  const parts = path.split("/").filter(Boolean);
  const fileStem = stemOf(path);

  if (fileStem === skuNorm || fileStem.startsWith(`${skuNorm}_`) || fileStem.startsWith(`${skuNorm}-`)) {
    return true;
  }

  if (parts.length >= 2) {
    const folder = parts[parts.length - 2];
    if (folder === skuNorm || folder.startsWith(`${skuNorm}_`) || folder.startsWith(`${skuNorm}-`)) {
      return true;
    }
    if (skuNorm.length >= 3 && folder.includes(skuNorm)) {
      return true;
    }
  }

  if (skuNorm.length >= 3 && path.includes(skuNorm)) {
    return true;
  }

  const tokens = fileStem.split(/[^a-z0-9]+/i).filter(Boolean);
  return tokens.includes(skuNorm);
}

function sortMatchedNames(names) {
  return [...names].sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" }));
}

export function buildUploadMap(files) {
  const uploads = {};
  (files || []).forEach((item) => {
    if (!item?.raw) return;
    const rel = normalizePath(item.name || item.raw?.name || "");
    if (!rel) return;
    uploads[rel] = item.raw;
    const base = rel.split("/").pop();
    if (base && !uploads[base]) uploads[base] = item.raw;
  });
  return uploads;
}

export function matchUploadFiles(sku, names, uploads) {
  const matched = [];
  const used = new Set();
  const skuNorm = normalizeSku(sku);

  for (const name of names || []) {
    const key = normalizePath(name);
    if (key && uploads[key] && !used.has(key)) {
      matched.push([name, uploads[key]]);
      used.add(key);
      continue;
    }
    const base = key.split("/").pop();
    if (base && uploads[base] && !used.has(base)) {
      matched.push([name, uploads[base]]);
      used.add(base);
    }
  }

  if (skuNorm) {
    const keys = sortMatchedNames(Object.keys(uploads));
    keys.forEach((filename) => {
      if (used.has(filename)) return;
      if (fileMatchesSku(filename, skuNorm)) {
        matched.push([filename, uploads[filename]]);
        used.add(filename);
      }
    });
  }

  return matched;
}

export function fileStorageKey(file) {
  return normalizePath(file?.webkitRelativePath || file?.name || "");
}
