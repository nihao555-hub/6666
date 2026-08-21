<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>发品习惯</h2>
        <p class="muted">跟货走的字段单独管：先建类目模板，没有模板时才用全局兜底。店铺政策在「店铺 → 店铺政策」里填。</p>
      </div>
    </div>

    <el-alert v-if="!store.shopId" type="info" show-icon :closable="false" title="请先选择店铺" description="在左侧切换当前店铺后再配置发品习惯。" />

    <el-tabs v-else v-model="tab" class="habit-tabs">
      <el-tab-pane label="类目模板" name="category">
        <p class="tab-intro muted">
          官方按叶子类目发品。画笔和家具的包装、单位、运费可以不一样——给每一类单独定习惯（店小秘 / 马帮同款做法）。
        </p>
        <div class="tab-toolbar">
          <el-button type="primary" @click="openNewTemplate">新建类目模板</el-button>
        </div>
        <el-table :data="templateRows" v-loading="templatesLoading">
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column label="类目" min-width="220">
            <template #default="{ row }">{{ row.category_name || "类目待定" }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160" align="right">
            <template #default="{ row }">
              <el-button text type="primary" @click="editTemplate(row)">编辑</el-button>
              <el-button text type="danger" @click="removeTemplate(row)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <div class="empty">还没有类目模板。成稿时会先用匹配类目的模板，没有才走全局兜底。</div>
          </template>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="全局兜底" name="fallback">
        <p class="tab-intro muted">
          仅在该叶子类目<strong>还没有模板</strong>时，用这里的单位、运费、包装等填空白。有类目模板时以模板为准。
        </p>
        <p v-if="fallbackSource.category_name" class="tab-intro muted">
          选项以「{{ fallbackSource.category_name }}」为例。可换参考类目查看字段有无。
        </p>
        <p v-if="fallbackSource.pulled?.length" class="tab-intro muted">
          刚从在线商品补上：{{ pulledLabels }}。只作兜底，不代表全店每一款。
        </p>
        <el-form v-loading="fallbackLoading" label-width="110px" class="fallback-form">
          <el-form-item label="参考类目">
            <el-button @click="categoryBrowser = true">{{ referenceCategoryName || "选择参考类目" }}</el-button>
            <div class="muted" style="margin-top: 6px">决定下拉选项和字段有无，不等于只对这个类目生效。</div>
          </el-form-item>
          <el-form-item v-for="field in productFields" :key="field.key" :label="field.label">
            <el-select
              v-model="fallbackDefaults[field.key]"
              :multiple="field.multiple"
              filterable
              clearable
              style="width: 100%"
              @change="rememberLabel(field)"
            >
              <el-option v-for="option in field.options" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
            <div v-if="field.hint" class="muted" style="margin-top: 6px">{{ field.hint }}</div>
          </el-form-item>
          <el-form-item label="常用包装">
            <div style="display: flex; gap: 8px">
              <el-input v-model="fallbackDefaults.pkgLength" placeholder="长 cm" />
              <el-input v-model="fallbackDefaults.pkgWidth" placeholder="宽 cm" />
              <el-input v-model="fallbackDefaults.pkgHeight" placeholder="高 cm" />
            </div>
          </el-form-item>
          <el-form-item label="常用重量">
            <el-input v-model="fallbackDefaults.pkgWeight" placeholder="kg" />
          </el-form-item>
          <el-form-item label="常用交期">
            <el-input v-model="fallbackDefaults.ladderPeriod" placeholder="15" />
            <div class="muted" style="margin-top: 6px">天数。单条货不一样就在草稿里改。</div>
          </el-form-item>
          <el-form-item label="品牌兜底">
            <el-input v-model="fallbackDefaults.brand" placeholder="全店只有一个品牌才填" />
          </el-form-item>
          <div style="display: flex; gap: 8px; flex-wrap: wrap">
            <el-button type="primary" :loading="fallbackSaving" @click="saveFallback">保存兜底</el-button>
            <el-button :loading="fallbackLoading" @click="reloadFallback(true)">从在线商品拉</el-button>
          </div>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="templateDrawer" :title="templateForm.id ? '编辑类目模板' : '新建类目模板'" size="460px">
      <el-form v-loading="templateOptionsLoading" label-width="100px">
        <el-form-item label="名称"><el-input v-model="templateForm.name" /></el-form-item>
        <el-form-item label="类目">
          <el-button @click="templateCategoryBrowser = true">{{ templateForm.category_name || "选择类目" }}</el-button>
        </el-form-item>
        <el-form-item v-for="field in templatePickable" :key="field.key" :label="field.label">
          <el-select v-model="templateForm.values[field.key]" :multiple="field.multiple" filterable clearable style="width: 100%">
            <el-option v-for="option in field.options" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="包装重量"><el-input v-model="templateForm.values.pkgWeight" /></el-form-item>
        <el-form-item label="包装尺寸">
          <div style="display: flex; gap: 8px">
            <el-input v-model="templateForm.values.pkgLength" placeholder="长" />
            <el-input v-model="templateForm.values.pkgWidth" placeholder="宽" />
            <el-input v-model="templateForm.values.pkgHeight" placeholder="高" />
          </div>
        </el-form-item>
        <el-form-item label="交期"><el-input v-model="templateForm.values.ladderPeriod" placeholder="天" /></el-form-item>
        <el-button type="primary" :loading="templateSaving" :disabled="!templateForm.category_id" @click="saveTemplate">保存</el-button>
      </el-form>
    </el-drawer>

    <CategoryPicker v-model="categoryBrowser" @pick="onReferenceCategory" />
    <CategoryPicker v-model="templateCategoryBrowser" @pick="onTemplateCategory" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import CategoryPicker from "../components/CategoryPicker.vue";
import { api } from "../api";
import { store } from "../store";

const PRODUCT_KEYS = [
  "priceUnit",
  "logisticsProperty",
  "shippingTemplateId",
  "ladderPeriod",
  "pkgWeight",
  "pkgLength",
  "pkgWidth",
  "pkgHeight",
  "brand",
];

const route = useRoute();
const router = useRouter();
const tab = ref(route.query.tab === "fallback" ? "fallback" : "category");

const templateRows = ref([]);
const templatesLoading = ref(false);
const templateDrawer = ref(false);
const templateSaving = ref(false);
const templateOptionsLoading = ref(false);
const templateOptionFields = ref([]);
const templateCategoryBrowser = ref(false);
const templateForm = reactive({
  id: "",
  name: "",
  category_id: "",
  category_name: "",
  values: {},
});

const fallbackLoading = ref(false);
const fallbackSaving = ref(false);
const fallbackSource = ref({ category_name: "", fields: [], pulled: [] });
const fallbackDefaults = ref({});
const fallbackLabels = ref({});
const referenceCategoryId = ref("");
const referenceCategoryName = ref("");
const categoryBrowser = ref(false);

const templatePickable = computed(() => templateOptionFields.value.filter((item) => item.kind === "select"));
const pickable = computed(() => (fallbackSource.value.fields || []).filter((item) => item.kind === "select"));
const productFields = computed(() => pickable.value.filter((item) => item.scope === "product"));
const pulledLabels = computed(() => {
  const names = {
    priceUnit: "单位",
    shippingTemplateId: "运费模板",
    logisticsProperty: "物流属性",
    pkgWeight: "包装重量",
    pkgLength: "包装长",
    pkgWidth: "包装宽",
    pkgHeight: "包装高",
    brand: "品牌",
    ladderPeriod: "交期",
  };
  return (fallbackSource.value.pulled || []).map((key) => names[key] || key).join("、");
});

function splitValues(value) {
  if (Array.isArray(value)) return value;
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function rememberLabel(field) {
  const chosen = fallbackDefaults.value[field.key];
  const picked = (Array.isArray(chosen) ? chosen : [chosen])
    .map((value) => field.options.find((option) => option.value === value)?.label)
    .filter(Boolean);
  fallbackLabels.value[field.key] = picked.join("、");
}

async function reloadTemplates() {
  if (!store.shopId) {
    templateRows.value = [];
    return;
  }
  templatesLoading.value = true;
  try {
    templateRows.value = await api.templates({ shop_id: store.shopId });
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    templatesLoading.value = false;
  }
}

function openNewTemplate() {
  templateForm.id = "";
  templateForm.name = "";
  templateForm.category_id = "";
  templateForm.category_name = "";
  templateForm.values = {};
  templateOptionFields.value = [];
  templateDrawer.value = true;
}

function editTemplate(row) {
  templateForm.id = row.id;
  templateForm.name = row.name;
  templateForm.category_id = row.category_id;
  templateForm.category_name = row.category_name || row.name;
  templateForm.values = { ...row.values };
  templateDrawer.value = true;
  loadTemplateOptions(row.category_id);
}

async function onTemplateCategory(node) {
  templateForm.category_id = node.category_id;
  templateForm.category_name = node.label;
  if (!templateForm.name) templateForm.name = node.label;
  await loadTemplateOptions(node.category_id);
}

async function loadTemplateOptions(categoryId) {
  if (!store.shopId || !categoryId) return;
  templateOptionsLoading.value = true;
  try {
    const data = await api.shopDefaultOptions(store.shopId, categoryId, { pull: false });
    templateOptionFields.value = data.fields || [];
    for (const field of templatePickable.value) {
      if (templateForm.values[field.key] == null || templateForm.values[field.key] === "") {
        templateForm.values[field.key] = field.value;
      }
    }
  } catch (error) {
    ElMessage.warning(error.message);
  } finally {
    templateOptionsLoading.value = false;
  }
}

async function saveTemplate() {
  templateSaving.value = true;
  const body = {
    shop_id: store.shopId,
    name: templateForm.name,
    category_id: templateForm.category_id,
    values: templateForm.values,
  };
  try {
    if (templateForm.id) await api.updateTemplate(templateForm.id, body);
    else await api.createTemplate(body);
    templateDrawer.value = false;
    await reloadTemplates();
    ElMessage.success("类目模板已保存");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    templateSaving.value = false;
  }
}

async function removeTemplate(row) {
  await api.deleteTemplate(row.id);
  await reloadTemplates();
  ElMessage.success("已删除");
}

async function reloadFallback(refresh = false) {
  if (!store.shopId) return;
  fallbackLoading.value = true;
  try {
    await store.loadShops();
    const shop = store.shops.find((item) => item.id === store.shopId);
    const saved = shop?.defaults || {};
    fallbackDefaults.value = {};
    for (const key of PRODUCT_KEYS) {
      fallbackDefaults.value[key] = saved[key] ?? "";
    }
    fallbackSource.value = await api.shopDefaultOptions(store.shopId, referenceCategoryId.value, { refresh });
    if (!referenceCategoryId.value && fallbackSource.value.category_name) {
      referenceCategoryName.value = fallbackSource.value.category_name;
    }
    for (const field of fallbackSource.value.fields || []) {
      if (field.kind === "unsupported" || field.scope !== "product") continue;
      if (fallbackDefaults.value[field.key] == null || fallbackDefaults.value[field.key] === "") {
        fallbackDefaults.value[field.key] = field.multiple ? splitValues(field.value) : field.value;
      }
      if (field.kind === "select") rememberLabel(field);
    }
    if (refresh && fallbackSource.value.pulled?.length) {
      ElMessage.success(`已从店里更新：${pulledLabels.value}`);
    }
  } catch (error) {
    ElMessage.warning(error.message);
  } finally {
    fallbackLoading.value = false;
  }
}

async function onReferenceCategory(node) {
  referenceCategoryId.value = node.category_id;
  referenceCategoryName.value = node.label;
  await reloadFallback(false);
}

async function saveFallback() {
  if (!store.shopId) return;
  fallbackSaving.value = true;
  try {
    await store.loadShops();
    const shop = store.shops.find((item) => item.id === store.shopId);
    const merged = { ...(shop?.defaults || {}), ...fallbackDefaults.value };
    for (const field of productFields.value) {
      if (field.multiple) merged[field.key] = splitValues(merged[field.key]).join(",");
    }
    await api.saveDefaults(store.shopId, {
      defaults: merged,
      labels: { ...(shop?.defaults?.labels || {}), ...fallbackLabels.value },
    });
    await store.loadShops();
    ElMessage.success("全局兜底已保存");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    fallbackSaving.value = false;
  }
}

onMounted(async () => {
  if (route.query.tab === "fallback") tab.value = "fallback";
  await reloadTemplates();
  await reloadFallback(false);
});

watch(
  () => store.shopId,
  async () => {
    await reloadTemplates();
    referenceCategoryId.value = "";
    referenceCategoryName.value = "";
    await reloadFallback(false);
  },
);

watch(tab, (value) => {
  router.replace({ path: "/habits", query: value === "fallback" ? { tab: "fallback" } : {} });
});
</script>

<style scoped>
.habit-tabs {
  margin-top: 4px;
}
.tab-intro {
  margin: 0 0 14px;
  max-width: 720px;
}
.tab-intro strong {
  font-weight: 600;
}
.tab-toolbar {
  margin-bottom: 12px;
}
.fallback-form {
  max-width: 520px;
  margin-top: 8px;
}
</style>
