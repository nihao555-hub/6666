<template>
  <el-dialog v-model="open" title="选择类目" width="980px" class="category-dialog" @open="onOpen">
    <p class="muted intro">
      左侧是国际站官方类目树；右侧是这家店常用叶子类目（最近选过、在线商品里出现过的）。
    </p>
    <div class="picker-layout">
      <section class="picker-main">
        <p class="muted crumbs">
          <span v-for="(node, index) in path" :key="node.category_id">
            <el-link type="primary" @click="openNode(node.category_id)">{{ node.name }}</el-link>
            <span v-if="index < path.length - 1"> / </span>
          </span>
          <el-link v-if="path.length" type="info" style="margin-left: 8px" @click="openNode('0')">回到顶层</el-link>
        </p>
        <div v-if="shopMissing" class="tree-empty">
          <p class="muted">还没有绑定店铺。请先在左侧栏选择店铺，或去「店铺」页完成授权。</p>
        </div>
        <div v-else-if="!loading && !children.length" class="tree-empty">
          <p class="muted">{{ treeError || "还没有拉到类目树。请确认店铺已登录，或点右侧常用类目。" }}</p>
          <el-button size="small" type="primary" :loading="loading" @click="retryRoot">重试拉取</el-button>
        </div>
        <el-table
          v-else
          v-loading="loading && !children.length"
          :data="children"
          height="420"
          empty-text="还没有拉到类目。请确认已登录店铺，或点右侧常用类目。"
          @row-click="(row) => openNode(row.category_id)"
        >
          <el-table-column label="类目" min-width="260">
            <template #default="{ row }">
              {{ row.label }}
              <span v-if="row.is_leaf" class="status-pill green" style="margin-left: 6px">可发布</span>
            </template>
          </el-table-column>
          <el-table-column width="110" align="right">
            <template #default="{ row }">
              <el-button v-if="row.is_leaf" text type="primary" @click.stop="pick(row)">选这个</el-button>
              <span v-else class="muted">进入</span>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <aside class="picker-side">
        <div class="side-block">
          <h4>商家常用类目</h4>
          <p class="muted side-note">来自这家店在线商品、草稿和最近选过的叶子类目。</p>
        </div>

        <div v-if="recent.length" class="side-block">
          <small>最近选过</small>
          <div class="used-list">
            <button
              v-for="item in recent"
              :key="`recent-${item.category_id}`"
              type="button"
              class="used-chip"
              @click="chooseUsed(item)"
            >
              <b>{{ item.path_label || item.label }}</b>
              <span class="muted">{{ usedHint(item) }}</span>
            </button>
          </div>
        </div>

        <div v-if="used.length" class="side-block">
          <small>店里上过</small>
          <div class="used-list">
            <button
              v-for="item in used"
              :key="item.category_id"
              type="button"
              class="used-chip"
              @click="chooseUsed(item)"
            >
              <b>{{ item.path_label || item.label }}</b>
              <span class="muted">{{ usedHint(item) }}</span>
            </button>
          </div>
        </div>

        <p v-if="sidebarError" class="muted side-empty side-error">{{ sidebarError }}</p>
        <p v-else-if="!loadingSide && !recent.length && !used.length" class="muted side-empty">
          还没有常用类目。先在线发几个货，或从左侧树里选一次，之后就会出现在这里。
        </p>
        <p v-if="loadingSide && !recent.length && !used.length" class="muted side-empty">正在拉常用类目…</p>
      </aside>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";
import {
  awaitCategoryPrefetch,
  invalidateCategoryCache,
  prefetchCategoryPicker,
  readCategoryCache,
  sidebarCacheKey,
  treeCacheKey,
  writeCategoryCache,
} from "../categoryPickerCache";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue", "pick"]);

const open = ref(props.modelValue);
const loading = ref(false);
const loadingSide = ref(false);
const children = ref([]);
const path = ref([]);
const recent = ref([]);
const used = ref([]);
const shopMissing = ref(false);
const treeError = ref("");
const sidebarError = ref("");

watch(
  () => props.modelValue,
  (value) => {
    open.value = value;
  },
);
watch(open, (value) => emit("update:modelValue", value));

function applySidebar(data) {
  if (!data) return false;
  recent.value = data.recent || [];
  used.value = data.used || [];
  return Boolean(recent.value.length || used.value.length);
}

function applyTree(data) {
  if (!data) return false;
  children.value = data.children || [];
  path.value = data.path || [];
  return children.value.length > 0;
}

function usedHint(item) {
  if (item.source === "recent") return "最近选过";
  if (item.source === "online") return `店里约 ${item.count} 个`;
  if (item.source === "draft") return "本地草稿用过";
  if (item.source === "template") return "刊登模板";
  if (item.source === "memory") return "以前确认过";
  return "以前选过";
}

function chooseUsed(item) {
  if (item.is_leaf) {
    pick(item);
    return;
  }
  openNode(item.category_id);
}

async function loadSidebar(options = {}) {
  const { silent = false, force = false } = options;
  sidebarError.value = "";
  if (!store.shopId) return;
  if (force) invalidateCategoryCache(sidebarCacheKey(store.shopId));
  const cached = force ? null : readCategoryCache(sidebarCacheKey(store.shopId));
  if (cached) applySidebar(cached);
  if (cached && !silent) loadingSide.value = false;
  else if (!cached) loadingSide.value = true;
  try {
    const data = await api.categorySidebar(store.shopId, force ? { refresh: true } : {});
    applySidebar(data);
    sidebarError.value = "";
    if ((data.used || []).length || (data.recent || []).length) {
      writeCategoryCache(sidebarCacheKey(store.shopId), data);
    }
  } catch (error) {
    if (!cached) {
      sidebarError.value = String(error.message || "常用类目拉取失败");
      if (!String(error.message || "").includes("登录") && !String(error.message || "").includes("授权")) {
        ElMessage.error(error.message);
      }
    }
  } finally {
    loadingSide.value = false;
  }
}

async function openNode(parent, options = {}) {
  const { force = false } = options;
  treeError.value = "";
  if (!store.shopId) {
    shopMissing.value = true;
    ElMessage.warning("先登录一个店铺");
    return;
  }
  shopMissing.value = false;
  const cacheKey = treeCacheKey(store.shopId, parent);
  if (force) invalidateCategoryCache(cacheKey);
  const cached = force ? null : readCategoryCache(cacheKey);
  if (cached) applyTree(cached);
  if (!cached || !children.value.length) loading.value = true;
  try {
    const data = await api.categories(store.shopId, parent);
    children.value = data.children || [];
    path.value = data.path || [];
    treeError.value = "";
    if (children.value.length) {
      writeCategoryCache(cacheKey, { children: children.value, path: path.value });
    } else {
      invalidateCategoryCache(cacheKey);
      treeError.value = parent === "0" ? "类目树暂时拉不到，请确认店铺已授权后重试" : "这个类目节点暂时没有子类目";
    }
  } catch (error) {
    invalidateCategoryCache(cacheKey);
    if (!cached) {
      children.value = [];
      treeError.value = String(error.message || "类目树拉取失败");
      ElMessage.error(error.message);
    }
  } finally {
    loading.value = false;
  }
}

function retryRoot() {
  void openNode("0", { force: true });
  void loadSidebar({ force: true });
}

async function onOpen() {
  shopMissing.value = false;
  treeError.value = "";
  sidebarError.value = "";
  if (store.user) {
    try {
      await store.ensureShops();
    } catch (error) {
      ElMessage.error(error.message || "店铺加载失败");
    }
  }
  if (!store.shopId) {
    shopMissing.value = true;
    children.value = [];
    recent.value = [];
    used.value = [];
    return;
  }
  applySidebar(readCategoryCache(sidebarCacheKey(store.shopId)));
  applyTree(readCategoryCache(treeCacheKey(store.shopId, "0")));
  const hadCache = children.value.length > 0;
  if (!hadCache) loading.value = true;
  if (!recent.value.length && !used.value.length) loadingSide.value = true;
  try {
    await awaitCategoryPrefetch(store.shopId);
    applySidebar(readCategoryCache(sidebarCacheKey(store.shopId)));
    applyTree(readCategoryCache(treeCacheKey(store.shopId, "0")));
  } catch {
    /* prefetch is best-effort */
  }
  await Promise.all([
    openNode("0", { force: false }),
    loadSidebar({ silent: Boolean(recent.value.length || used.value.length) }),
  ]);
  if (!children.value.length && !loading.value) {
    void prefetchCategoryPicker(store.shopId);
  }
}

function pathLabel(node) {
  const crumbs = path.value.map((item) => item.name || item.label || item.cn_name).filter(Boolean);
  const leaf = node.label || node.name || node.cn_name || "";
  const bits = [...crumbs];
  if (leaf && !bits.some((item) => item === leaf || String(item).includes(leaf))) bits.push(leaf);
  return bits.join(" / ");
}

function pick(row) {
  const payload = { ...row, path_label: row.path_label || pathLabel(row) };
  emit("pick", payload);
  open.value = false;
  void recordPick(payload);
}

async function recordPick(payload) {
  if (!payload.category_id) return;
  try {
    await store.ensureShops();
    if (!store.shopId) return;
    await api.recordCategoryPick(store.shopId, {
      category_id: payload.category_id,
      category_name: payload.path_label || payload.label || payload.name || "",
    });
    invalidateCategoryCache(sidebarCacheKey(store.shopId));
  } catch {
    /* remembering recent picks is optional */
  }
}
</script>

<style scoped>
.intro {
  margin: 0 0 12px;
}
.picker-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(260px, 0.85fr);
  gap: 14px;
  min-height: 460px;
}
.picker-main {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 10px 12px 12px;
  background: var(--surface);
}
.picker-side {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px;
  background: var(--gray3);
  overflow: auto;
  max-height: 460px;
}
.crumbs {
  margin: 0 0 10px;
  min-height: 22px;
}
.tree-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  min-height: 420px;
  justify-content: center;
  padding: 12px 0;
}
.tree-empty p {
  margin: 0;
}
.side-block + .side-block {
  margin-top: 14px;
}
.side-block h4 {
  margin: 0 0 4px;
  font-size: 14px;
}
.side-note,
.side-empty {
  margin: 0;
  font-size: 12px;
}
.side-error {
  color: #b45309;
}
.side-block small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 8px;
}
.used-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.used-chip {
  text-align: left;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: var(--radius);
  padding: 8px 10px;
  cursor: pointer;
  font: inherit;
  color: inherit;
  width: 100%;
}
.used-chip:hover {
  border-color: var(--accent-line);
  background: var(--accent-wash);
}
.used-chip b {
  display: block;
  font-size: 13px;
  font-weight: 600;
}
@media (max-width: 860px) {
  .picker-layout {
    grid-template-columns: 1fr;
  }
  .picker-side {
    max-height: none;
  }
}
</style>
