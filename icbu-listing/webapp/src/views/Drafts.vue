<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>草稿箱</h2>
        <p class="muted">只处理红项和黄项。绿的勾上直接进队列。</p>
      </div>
      <div>
        <el-button :disabled="!selected.length" @click="publishSelected">
          批量发布（{{ selected.length }}）
        </el-button>
        <el-button type="primary" @click="selectReady">一键选中可发布</el-button>
      </div>
    </div>

    <div class="toolbar">
      <div class="filter-pills">
        <button class="filter-pill" :class="{ 'is-on': status === '' }" @click="setStatus('')">全部 {{ counts.all }}</button>
        <button class="filter-pill" :class="{ 'is-on': status === 'red' }" @click="setStatus('red')">红 {{ counts.red }}</button>
        <button class="filter-pill" :class="{ 'is-on': status === 'yellow' }" @click="setStatus('yellow')">黄 {{ counts.yellow }}</button>
        <button class="filter-pill" :class="{ 'is-on': status === 'green' }" @click="setStatus('green')">绿 {{ counts.green }}</button>
        <button class="filter-pill" :class="{ 'is-on': status === 'failed' }" @click="setStatus('failed')">失败 {{ counts.failed }}</button>
        <button class="filter-pill" :class="{ 'is-on': status === 'published' }" @click="setStatus('published')">已发布 {{ counts.published }}</button>
      </div>
      <div class="spacer"></div>
      <el-button text @click="reload">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" @selection-change="onSelect" row-key="id">
      <el-table-column type="selection" width="44" :selectable="isSelectable" />
      <el-table-column label="标题" min-width="280">
        <template #default="{ row }">
          <div class="record">
            <img v-if="row.images?.[0]" :src="row.images[0].preview" class="thumb" />
            <span v-else class="record-mark">{{ (row.sku || "货").slice(0, 1) }}</span>
            <div>
              <div>{{ row.title || "（还没有标题）" }}</div>
              <span class="muted">{{ row.category_name || "类目待定" }}</span>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="96">
        <template #default="{ row }">
          <span class="status-pill" :class="row.status">{{ label(row.status) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="sku" label="货号" width="130" show-overflow-tooltip />
      <el-table-column v-if="!shopFilter" label="店铺" width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.shop_name || "—" }}</template>
      </el-table-column>
      <el-table-column label="质量分" width="88">
        <template #default="{ row }">
          <span :class="{ 'text-red': row.quality && !row.quality.ready }">
            {{ row.quality?.score != null ? row.quality.score.toFixed(1) : "—" }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="价格 / 起订" width="130">
        <template #default="{ row }">
          <span :class="{ 'text-red': !row.price || !row.moq }">
            {{ row.price || "—" }} / {{ row.moq || "—" }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="待处理" min-width="260">
        <template #default="{ row }">
          <span v-if="!row.issues?.length" class="muted">没有问题</span>
          <span v-for="issue in row.issues.slice(0, 3)" :key="issue.path" class="issue-line">
            <i class="dot" :class="issue.level"></i>{{ issue.field_name }}：{{ issue.message }}
          </span>
          <span v-if="row.issues?.length > 3" class="muted">还有 {{ row.issues.length - 3 }} 条</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="$router.push(`/drafts/${row.id}`)">审稿</el-button>
          <el-button text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty">
          <img class="empty-art" src="/art/empty-drafts.png" alt="" />
          <b>还没有草稿</b>
          去「投料」丢图或传回表格即可。
        </div>
      </template>
    </el-table>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const route = useRoute();
const rows = ref([]);
const all = ref([]);
const loading = ref(false);
const status = ref("");
const selected = ref([]);
const shopFilter = ref(route.query.shop === "all" ? "" : store.shopId || "");

const counts = computed(() => {
  const base = { all: all.value.length, red: 0, yellow: 0, green: 0, failed: 0, published: 0 };
  all.value.forEach((item) => {
    if (base[item.status] !== undefined) base[item.status] += 1;
  });
  return base;
});

function setStatus(value) {
  status.value = value;
  reload();
}

function label(value) {
  return { red: "待处理", yellow: "可略过", green: "就绪", publishing: "发布中", published: "已发布", failed: "失败" }[value] || value;
}

function isSelectable(row) {
  return ["green", "yellow", "failed"].includes(row.status);
}

async function reload() {
  loading.value = true;
  try {
    all.value = await api.drafts(shopFilter.value ? { shop_id: shopFilter.value } : {});
    rows.value = status.value ? all.value.filter((item) => item.status === status.value) : all.value;
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

onMounted(reload);

function onSelect(items) {
  selected.value = items;
}

function selectReady() {
  status.value = "green";
  reload();
}

async function publishSelected() {
  try {
    const result = await api.publishMany(selected.value.map((item) => item.id));
    ElMessage.success(`已排队 ${result.queued} 条，去发布队列看结果`);
    setTimeout(reload, 1200);
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function remove(row) {
  await api.deleteDraft(row.id);
  await reload();
}
</script>

<style scoped>
.text-red {
  color: #f56c6c;
}
</style>
