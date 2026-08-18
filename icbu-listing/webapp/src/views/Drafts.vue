<template>
  <div class="page">
    <el-alert
      v-if="batchId"
      type="info"
      show-icon
      :closable="false"
      style="margin-bottom: 14px"
      title="当前只看本批导入"
      :description="`本批 ${rows.length} 条。审完可批量发布。`"
    />
    <div v-if="batchId" style="margin: -6px 0 14px">
      <el-button text type="primary" @click="clearBatch">看全部商品</el-button>
    </div>

    <div class="page-head">
      <div>
        <h2>商品</h2>
        <p class="muted">填完短表、AI 成稿之后还不能发。每条打开看标题和官方属性，点「审过了」才能发。选错但合法的选项（HB 写成 2B）只能人看出来。</p>
      </div>
      <div v-if="tab === 'local'">
        <el-button :disabled="!selected.length" @click="publishSelected">
          批量发布（{{ selected.length }}）
        </el-button>
        <el-button type="primary" @click="selectReady">一键选中已审可发</el-button>
      </div>
    </div>

    <div class="toolbar">
      <div class="filter-pills">
        <button class="filter-pill" :class="{ 'is-on': tab === 'local' }" @click="setTab('local')">本平台</button>
        <button class="filter-pill" :class="{ 'is-on': tab === 'live' }" @click="setTab('live')">店里在售</button>
      </div>
      <div v-if="tab === 'local'" class="filter-pills" style="margin-left: 8px">
        <button class="filter-pill" :class="{ 'is-on': filter === '' }" @click="setFilter('')">全部 {{ counts.all }}</button>
        <button class="filter-pill" :class="{ 'is-on': filter === 'pending' }" @click="setFilter('pending')">待审 {{ counts.pending }}</button>
        <button class="filter-pill" :class="{ 'is-on': filter === 'red' }" @click="setFilter('red')">待改 {{ counts.red }}</button>
        <button class="filter-pill" :class="{ 'is-on': filter === 'ready' }" @click="setFilter('ready')">已审可发 {{ counts.ready }}</button>
        <button class="filter-pill" :class="{ 'is-on': filter === 'failed' }" @click="setFilter('failed')">失败 {{ counts.failed }}</button>
        <button class="filter-pill" :class="{ 'is-on': filter === 'published' }" @click="setFilter('published')">已发布 {{ counts.published }}</button>
      </div>
      <div class="spacer"></div>
      <el-button text @click="reload">刷新</el-button>
    </div>

    <el-table v-if="tab === 'local'" :data="rows" v-loading="loading" @selection-change="onSelect" row-key="id">
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
      <el-table-column label="状态" width="150">
        <template #default="{ row }">
          <span class="status-pill" :class="row.status">{{ label(row.status) }}</span>
          <span v-if="!row.reviewed && !['published', 'publishing'].includes(row.status)" class="status-pill yellow" style="margin-left: 4px">待审</span>
          <span v-else-if="row.reviewed && !['published', 'publishing'].includes(row.status)" class="status-pill green" style="margin-left: 4px">已审</span>
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
      <el-table-column label="待处理" min-width="240">
        <template #default="{ row }">
          <span v-if="!row.issues?.length" class="muted">没有问题</span>
          <span v-for="issue in row.issues.slice(0, 3)" :key="issue.path" class="issue-line">
            <i class="dot" :class="issue.level"></i>{{ issue.field_name }}：{{ issue.message }}
          </span>
          <span v-if="row.issues?.length > 3" class="muted">还有 {{ row.issues.length - 3 }} 条</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="130" align="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="$router.push(`/drafts/${row.id}`)">核对</el-button>
          <el-button text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty">
          <img class="empty-art" src="/art/empty-drafts.png" alt="" />
          <b>还没有商品</b>
          去「投料」丢图或传回表格即可。
        </div>
      </template>
    </el-table>

    <el-table v-else :data="liveRows" v-loading="liveLoading">
      <el-table-column label="图" width="70">
        <template #default="{ row }">
          <img v-if="row.image" :src="row.image" class="thumb" />
        </template>
      </el-table-column>
      <el-table-column prop="subject" label="店里标题" min-width="320" show-overflow-tooltip />
      <el-table-column prop="modified" label="更新时间" width="200" />
      <el-table-column label="操作" width="160" align="right">
        <template #default="{ row }">
          <el-button text type="primary" :loading="busy === row.id" @click="pullLive(row)">拉回来改</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty">
          <img class="empty-art" src="/art/empty-queue.png" alt="" />
          <b>店里还没有在售商品</b>
          先去投料上品，发成功后会出现在这里。
        </div>
      </template>
    </el-table>
    <el-pagination
      v-if="tab === 'live'"
      style="margin-top: 14px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="liveTotal"
      :page-size="20"
      :current-page="livePage"
      @current-change="onLivePage"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const route = useRoute();
const router = useRouter();
const rows = ref([]);
const all = ref([]);
const loading = ref(false);
const filter = ref(route.query.filter || "");
const batchId = ref(route.query.batch_id || "");
const selected = ref([]);
const shopFilter = ref(route.query.shop === "all" ? "" : store.shopId || "");
const tab = ref(route.query.tab === "live" ? "live" : "local");
const liveRows = ref([]);
const liveTotal = ref(0);
const livePage = ref(1);
const liveLoading = ref(false);
const busy = ref("");

const counts = computed(() => {
  const base = { all: all.value.length, red: 0, yellow: 0, green: 0, failed: 0, published: 0, pending: 0, ready: 0 };
  all.value.forEach((item) => {
    if (base[item.status] !== undefined) base[item.status] += 1;
    if (!item.reviewed && !["published", "publishing"].includes(item.status)) base.pending += 1;
    if (item.reviewed && ["green", "yellow"].includes(item.status)) base.ready += 1;
  });
  return base;
});

function setTab(value) {
  tab.value = value;
  reload();
}

function setFilter(value) {
  filter.value = value;
  reload();
}

function label(value) {
  return { red: "待改", yellow: "可略过", green: "校验过", publishing: "发布中", published: "已发布", failed: "失败" }[value] || value;
}

function isSelectable(row) {
  return Boolean(row.reviewed) && ["green", "yellow", "failed"].includes(row.status);
}

function matches(item) {
  if (!filter.value) return true;
  if (filter.value === "pending") return !item.reviewed && !["published", "publishing"].includes(item.status);
  if (filter.value === "ready") return Boolean(item.reviewed) && ["green", "yellow"].includes(item.status);
  return item.status === filter.value;
}

async function reload() {
  if (tab.value === "live") {
    await loadLive();
    return;
  }
  loading.value = true;
  try {
    const params = {};
    if (shopFilter.value) params.shop_id = shopFilter.value;
    if (batchId.value) params.batch_id = batchId.value;
    all.value = await api.drafts(params);
    rows.value = all.value.filter(matches);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function clearBatch() {
  batchId.value = "";
  router.replace({ path: "/drafts", query: { ...(filter.value ? { filter: filter.value } : {}) } });
  reload();
}

async function loadLive() {
  if (!store.shopId) {
    liveRows.value = [];
    return;
  }
  liveLoading.value = true;
  try {
    const data = await api.onlineProducts(store.shopId, {
      page: livePage.value,
      page_size: 20,
      filter_type: "onSelling",
    });
    liveRows.value = data.products || [];
    liveTotal.value = data.total || 0;
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    liveLoading.value = false;
  }
}

function onLivePage(value) {
  livePage.value = value;
  loadLive();
}

onMounted(reload);

function onSelect(items) {
  selected.value = items;
}

function selectReady() {
  filter.value = "ready";
  reload();
}

async function publishSelected() {
  try {
    const result = await api.publishMany(selected.value.map((item) => item.id));
    ElMessage.success(`已排队 ${result.queued} 条，去队列看进度`);
    setTimeout(reload, 1200);
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function pullLive(row) {
  if (!store.shopId || !row.category_id) {
    ElMessage.warning("这条没有类目，不能拉回来");
    return;
  }
  busy.value = row.id;
  try {
    const draft = await api.cloneOnline(store.shopId, {
      product_id: row.id,
      category_id: row.category_id,
      differentiate: true,
    });
    ElMessage.success("已拉回。标题已换过，改完再发。");
    router.push(`/drafts/${draft.id}`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    busy.value = "";
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
