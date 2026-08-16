<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>队列</h2>
        <p class="muted">失败原因翻成人话，改完可以直接重发。关掉页面也不影响。</p>
      </div>
      <el-button @click="reload">刷新</el-button>
    </div>

    <div class="toolbar">
      <el-select v-model="shopFilter" placeholder="全部店铺" clearable style="width: 200px" @change="reload">
        <el-option label="全部店铺" value="" />
        <el-option v-for="shop in store.shops" :key="shop.id" :label="shop.name" :value="shop.id" />
      </el-select>
    </div>

    <el-table :data="rows" v-loading="loading">
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="tagType(row.status)" size="small">{{ label(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="模式" width="100">
        <template #default="{ row }">{{ row.mode === "online" ? "直接上架" : "官方草稿" }}</template>
      </el-table-column>
      <el-table-column prop="sku" label="货号" width="130" show-overflow-tooltip />
      <el-table-column v-if="!shopFilter" label="店铺" width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.shop_name || "—" }}</template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
      <el-table-column label="商品 ID" width="160">
        <template #default="{ row }">{{ row.product_id || "—" }}</template>
      </el-table-column>
      <el-table-column label="失败原因" min-width="280">
        <template #default="{ row }">
          <span v-if="!row.error" class="muted">—</span>
          <span v-else>{{ row.error }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="right">
        <template #default="{ row }">
          <el-button v-if="row.status === 'failed'" text type="primary" @click="retry(row)">重发</el-button>
          <el-button text @click="$router.push(`/drafts/${row.draft_id}`)">看草稿</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty">还没有发布记录。</div>
      </template>
    </el-table>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const rows = ref([]);
const loading = ref(false);
const shopFilter = ref("");
let timer = null;

function tagType(value) {
  return { success: "success", failed: "danger", running: "warning", queued: "info" }[value] || "info";
}

function label(value) {
  return { success: "成功", failed: "失败", running: "发布中", queued: "排队中" }[value] || value;
}

async function reload() {
  loading.value = true;
  try {
    rows.value = await api.jobs(shopFilter.value ? { shop_id: shopFilter.value } : {});
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  reload();
  timer = setInterval(reload, 5000);
});

onUnmounted(() => clearInterval(timer));

async function retry(row) {
  try {
    const job = await api.retryJob(row.id);
    ElMessage[job.status === "success" ? "success" : "error"](job.status === "success" ? "重发成功" : job.error);
    await reload();
  } catch (error) {
    ElMessage.error(error.message);
  }
}
</script>
