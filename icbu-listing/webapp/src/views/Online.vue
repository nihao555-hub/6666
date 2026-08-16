<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>在线商品</h2>
        <p class="muted">
          实时打当前店铺的接口，不是平台公共库。改价、上下架需要额外的接口权限，当前应用还没有开通。
        </p>
      </div>
      <el-select v-model="filterType" style="width: 160px" @change="reload">
        <el-option label="在售" value="onSelling" />
        <el-option label="已下架" value="expired" />
      </el-select>
    </div>

    <el-table :data="rows" v-loading="loading">
      <el-table-column label="图" width="70">
        <template #default="{ row }">
          <img v-if="row.image" :src="row.image" class="thumb" />
        </template>
      </el-table-column>
      <el-table-column prop="subject" label="标题" min-width="320" show-overflow-tooltip />
      <el-table-column prop="category_id" label="类目 ID" width="130" />
      <el-table-column prop="modified" label="更新时间" width="200" />
    </el-table>

    <el-pagination
      style="margin-top: 14px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="20"
      :current-page="page"
      @current-change="onPage"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const rows = ref([]);
const total = ref(0);
const page = ref(1);
const filterType = ref("onSelling");
const loading = ref(false);

async function reload() {
  if (!store.shopId) return;
  loading.value = true;
  try {
    const data = await api.onlineProducts(store.shopId, {
      page: page.value,
      page_size: 20,
      filter_type: filterType.value,
    });
    rows.value = data.products;
    total.value = data.total;
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

onMounted(reload);

function onPage(value) {
  page.value = value;
  reload();
}
</script>
