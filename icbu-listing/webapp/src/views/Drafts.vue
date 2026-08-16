<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>草稿箱</h2>
        <p class="muted">只处理红项和黄项。绿的勾上直接进发布队列，不用逐条点开。</p>
      </div>
      <div>
        <el-button :disabled="!selected.length" @click="publishSelected">
          批量发布（{{ selected.length }}）
        </el-button>
        <el-button type="primary" @click="selectReady">一键选中可发布</el-button>
      </div>
    </div>

    <div class="toolbar">
      <el-select v-model="shopFilter" placeholder="全部店铺" clearable style="width: 200px" @change="reload">
        <el-option label="全部店铺" value="" />
        <el-option v-for="shop in store.shops" :key="shop.id" :label="shop.name" :value="shop.id" />
      </el-select>
      <el-radio-group v-model="status" @change="reload">
        <el-radio-button value="">全部 {{ counts.all }}</el-radio-button>
        <el-radio-button value="red">红 {{ counts.red }}</el-radio-button>
        <el-radio-button value="yellow">黄 {{ counts.yellow }}</el-radio-button>
        <el-radio-button value="green">绿 {{ counts.green }}</el-radio-button>
        <el-radio-button value="failed">失败 {{ counts.failed }}</el-radio-button>
        <el-radio-button value="published">已发布 {{ counts.published }}</el-radio-button>
      </el-radio-group>
      <div class="spacer"></div>
      <el-button text @click="reload">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" @selection-change="onSelect" row-key="id">
      <el-table-column type="selection" width="44" :selectable="isSelectable" />
      <el-table-column label="图" width="70">
        <template #default="{ row }">
          <img v-if="row.images?.[0]" :src="row.images[0].preview" class="thumb" />
          <div v-else class="thumb"></div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="96">
        <template #default="{ row }">
          <el-tag :type="tagType(row.status)" size="small">{{ label(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="sku" label="货号" width="130" show-overflow-tooltip />
      <el-table-column v-if="!shopFilter" label="店铺" width="140" show-overflow-tooltip>
        <template #default="{ row }">{{ row.shop_name || "—" }}</template>
      </el-table-column>
      <el-table-column label="标题 / 类目" min-width="300">
        <template #default="{ row }">
          <div>{{ row.title || "（还没有标题）" }}</div>
          <span class="muted">{{ row.category_name || "类目待定" }}</span>
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
        <div class="empty">还没有草稿，先去投料。</div>
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

function tagType(value) {
  return { red: "danger", yellow: "warning", green: "success", published: "success", failed: "danger" }[value] || "info";
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
