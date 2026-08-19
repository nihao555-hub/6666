<template>
  <el-dialog v-model="open" title="选择类目" width="640px" @open="openNode('0')">
    <p class="muted" style="margin-bottom: 8px">
      这是国际站官方类目树，和后台选类目是同一棵。所有店铺看到的一级都一样，不是店里自建的分类。
    </p>
    <div v-if="recent.length" class="used-box is-recent">
      <small>最近选过</small>
      <p class="muted" style="margin: 4px 0 8px">在这家店选过的叶子类目，点一下直接选用。</p>
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
    <div v-if="used.length" class="used-box">
      <small>这家店已经上过的</small>
      <p class="muted" style="margin: 4px 0 8px">从在线商品和本地草稿汇总，点一下就能选到可发布的叶子。</p>
      <div class="used-list">
        <button
          v-for="item in used"
          :key="item.category_id"
          type="button"
          class="used-chip"
          @click="chooseUsed(item)"
        >
          <b>{{ item.label }}</b>
          <span class="muted">{{ usedHint(item) }}</span>
        </button>
      </div>
    </div>
    <p class="muted" style="margin-bottom: 10px">
      <span v-for="(node, index) in path" :key="node.category_id">
        <el-link type="primary" @click="openNode(node.category_id)">{{ node.name }}</el-link>
        <span v-if="index < path.length - 1"> / </span>
      </span>
      <el-link v-if="path.length" type="info" style="margin-left: 8px" @click="openNode('0')">回到顶层</el-link>
    </p>
    <el-table :data="children" height="360" @row-click="(row) => openNode(row.category_id)">
      <el-table-column label="类目" min-width="240">
        <template #default="{ row }">
          {{ row.label }}
          <span v-if="row.is_leaf" class="status-pill green" style="margin-left: 6px">可发布</span>
        </template>
      </el-table-column>
      <el-table-column width="110" align="right">
        <template #default="{ row }">
          <el-button v-if="row.is_leaf" text type="primary" @click.stop="pick(row)">选这个</el-button>
        </template>
      </el-table-column>
    </el-table>
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
const children = ref([]);
const path = ref([]);
const recent = ref([]);
const used = ref([]);

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

async function openNode(parent) {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  try {
    const data = await api.categories(store.shopId, parent);
    children.value = data.children || [];
    path.value = data.path || [];
    if (parent === "0") {
      recent.value = data.recent || [];
      used.value = data.used || [];
    }
  } catch (error) {
    ElMessage.error(error.message);
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
  if (store.shopId && payload.category_id) {
    api
      .recordCategoryPick(store.shopId, {
        category_id: payload.category_id,
        category_name: payload.path_label || payload.label || payload.name || "",
      })
      .catch(() => {});
  }
}
</script>

<style scoped>
.used-box {
  margin: 0 0 14px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--gray3);
}
.used-box.is-recent {
  border-color: var(--accent-line);
  background: var(--accent-wash);
}
.used-box small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
}
.used-list {
  display: flex;
  flex-wrap: wrap;
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
  max-width: 100%;
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
</style>
