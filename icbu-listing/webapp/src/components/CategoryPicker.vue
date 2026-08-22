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
        <el-table
          v-loading="loading"
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

        <p v-if="!loadingSide && !recent.length && !used.length" class="muted side-empty">
          还没有常用类目。先在线发几个货，或从左侧树里选一次，之后就会出现在这里。
        </p>
        <p v-if="loadingSide" class="muted side-empty">正在拉常用类目…</p>
      </aside>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

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
const sideLoaded = ref(false);

watch(
  () => props.modelValue,
  (value) => {
    open.value = value;
  },
);
watch(open, (value) => emit("update:modelValue", value));

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

async function loadSidebar() {
  if (!store.shopId) return;
  loadingSide.value = true;
  try {
    const data = await api.categorySidebar(store.shopId);
    recent.value = data.recent || [];
    used.value = data.used || [];
    sideLoaded.value = true;
  } catch (error) {
    if (!String(error.message || "").includes("登录")) {
      ElMessage.error(error.message);
    }
  } finally {
    loadingSide.value = false;
  }
}

async function openNode(parent) {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  loading.value = true;
  try {
    const data = await api.categories(store.shopId, parent);
    children.value = data.children || [];
    path.value = data.path || [];
  } catch (error) {
    children.value = [];
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function onOpen() {
  sideLoaded.value = false;
  recent.value = [];
  used.value = [];
  if (store.user) {
    try {
      await store.ensureShops();
    } catch {
      /* shop binding happens on Feed mount */
    }
  }
  await Promise.all([openNode("0"), loadSidebar()]);
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
