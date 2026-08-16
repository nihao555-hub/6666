<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>投料上品</h2>
        <p class="muted">
          你只提供机器推不出来的东西：图、价格、起订量。类目、属性、英文标题、关键词、详情由 AI 按官方规则生成。
          投料会同时写入「商品库」——多店时不用重新丢图，去商品库勾店铺铺货即可。
        </p>
      </div>
    </div>

    <el-alert
      v-if="!store.shopId"
      type="warning"
      show-icon
      :closable="false"
      title="先绑一个店铺"
      description="投料需要用店铺的授权去拿类目规则和上传图片银行。"
      style="margin-bottom: 14px"
    />

    <el-tabs v-model="tab">
      <el-tab-pane label="Excel 导入" name="excel">
        <div class="card">
          <p class="muted" style="margin-bottom: 14px">
            对齐头部 ERP 的几种做法，选你熟悉的那一种。先下载模板或直接丢现有表格，系统探测表头，你确认列映射后再导入。
          </p>
          <el-radio-group v-model="excel.style" class="style-grid" @change="onStyleChange">
            <el-radio-button v-for="item in styles" :key="item.id" :value="item.id">
              {{ item.label }}
            </el-radio-button>
          </el-radio-group>
          <p class="muted" style="margin: 12px 0 16px">{{ currentStyle?.summary }}</p>

          <el-form label-width="120px" style="max-width: 720px">
            <el-form-item v-if="currentStyle?.needs_listing_template" label="刊登模板">
              <el-select v-model="excel.listingTemplateId" placeholder="先选一个类目模板" style="width: 320px">
                <el-option
                  v-for="item in listingTemplates"
                  :key="item.id"
                  :label="`${item.name} · ${item.category_id}`"
                  :value="item.id"
                />
              </el-select>
              <div class="muted">没有模板就去「刊登模板」建一个。表格里不用再填类目和物流。</div>
            </el-form-item>
            <el-form-item label="Excel 模板">
              <el-button @click="downloadTemplate">下载 {{ currentStyle?.label || "" }} 模板</el-button>
            </el-form-item>
            <el-form-item label="填好的表格">
              <el-upload v-model:file-list="excelFile" :auto-upload="false" :limit="1" accept=".xlsx,.xlsm,.xls">
                <el-button>选择 xlsx</el-button>
              </el-upload>
            </el-form-item>
            <el-form-item label="配套图片">
              <el-upload v-model:file-list="excelImages" :auto-upload="false" multiple accept="image/*" drag>
                <div style="padding: 18px 0">可选。按货号前缀匹配，例如 SKU-1001_1.jpg</div>
              </el-upload>
            </el-form-item>
            <el-form-item label="导入后">
              <el-checkbox v-model="excel.createDrafts" :disabled="currentStyle?.needs_listing_template">
                同时生成当前店草稿
              </el-checkbox>
            </el-form-item>
            <el-button :loading="excel.loading" :disabled="!excelFile.length" @click="previewExcel">探测表头</el-button>
            <el-button
              type="primary"
              :loading="excel.loading"
              :disabled="!excel.preview"
              @click="importExcel"
            >
              确认导入
            </el-button>
          </el-form>

          <div v-if="excel.preview" style="margin-top: 18px">
            <p>
              识别到 {{ excel.preview.row_count }} 行，表头在第 {{ excel.preview.header_row }} 行。
              猜测风格：{{ styleLabel(excel.preview.style_guess) }}。请确认下面的列映射。
            </p>
            <el-alert
              v-for="warning in excel.preview.warnings || []"
              :key="warning"
              type="warning"
              :title="warning"
              :closable="false"
              style="margin-bottom: 8px"
            />
            <el-table :data="mappingRows" size="small" style="max-width: 640px; margin: 12px 0">
              <el-table-column prop="header" label="表格列" />
              <el-table-column label="对到系统字段">
                <template #default="{ row }">
                  <el-select v-model="excel.mapping[row.header]" clearable placeholder="忽略这一列">
                    <el-option v-for="field in excel.preview.fields" :key="field.id" :label="field.label" :value="field.id" />
                  </el-select>
                </template>
              </el-table-column>
            </el-table>
            <el-table :data="excel.preview.rows_preview" size="small" max-height="240">
              <el-table-column
                v-for="header in excel.preview.headers"
                :key="header"
                :prop="header"
                :label="header"
                min-width="120"
                show-overflow-tooltip
              />
            </el-table>
          </div>

          <el-divider v-if="excel.batch" />
          <div v-if="excel.batch">
            <p>
              批次 {{ excel.batch.batch_id.slice(0, 8) }}：共 {{ excel.batch.count }} 行，已入库
              {{ excelProgress.done }} 个。
            </p>
            <el-progress :percentage="excelPercent" :stroke-width="14" />
            <el-button style="margin-top: 12px" @click="$router.push('/products')">去商品库</el-button>
            <el-button v-if="excel.batch.create_drafts" style="margin-top: 12px" @click="$router.push('/drafts')">
              去草稿箱
            </el-button>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="单条上品" name="single">
        <div class="card">
          <el-form label-width="96px" style="max-width: 620px">
            <el-form-item label="产品图">
              <el-upload
                v-model:file-list="files"
                list-type="picture-card"
                :auto-upload="false"
                :limit="6"
                accept="image/*"
              >
                <span style="font-size: 22px">+</span>
              </el-upload>
              <div class="muted">1～6 张。第一张作主图，会先进图片银行再发布。</div>
            </el-form-item>
            <el-form-item label="货号">
              <el-input v-model="form.sku" placeholder="留空则用图片文件名" />
            </el-form-item>
            <el-form-item label="单价">
              <el-input v-model="form.price" placeholder="12.50">
                <template #append>USD</template>
              </el-input>
            </el-form-item>
            <el-form-item label="起订量">
              <el-input v-model="form.moq" placeholder="100" />
            </el-form-item>
            <el-form-item label="补充说明">
              <el-input
                v-model="form.note"
                type="textarea"
                :rows="2"
                placeholder="可选。中文也行，例如：加厚款，可定制 logo"
              />
            </el-form-item>
            <el-button type="primary" :loading="loading" :disabled="!store.shopId" @click="submitOne">
              生成草稿
            </el-button>
            <span v-if="loading" class="muted" style="margin-left: 12px">
              正在看图、定类目、拉规则、写文案，大约 20～40 秒
            </span>
          </el-form>
        </div>
      </el-tab-pane>

      <el-tab-pane label="批量上品" name="batch">
        <div class="card">
          <p class="muted" style="margin-bottom: 14px">
            按工厂习惯来：图片名以货号开头，<code>SKU-1001_1.jpg</code> 和 <code>SKU-1001_2.jpg</code>
            会自动归成同一个商品，并写入商品库。价格和起订量整批统一，进草稿箱后可以逐条改。
          </p>
          <el-form label-width="96px" style="max-width: 620px">
            <el-form-item label="图片">
              <el-upload
                v-model:file-list="batchFiles"
                :auto-upload="false"
                multiple
                accept="image/*"
                drag
                style="width: 100%"
              >
                <div style="padding: 26px 0">把整个文件夹的图拖进来</div>
              </el-upload>
            </el-form-item>
            <el-form-item label="统一单价">
              <el-input v-model="form.price" placeholder="12.50" />
            </el-form-item>
            <el-form-item label="统一起订量">
              <el-input v-model="form.moq" placeholder="100" />
            </el-form-item>
            <el-button type="primary" :loading="loading" :disabled="!store.shopId" @click="submitBatch">
              开始批量成稿
            </el-button>
          </el-form>

          <el-divider v-if="batch" />
          <div v-if="batch">
            <p>
              批次 {{ batch.batch_id.slice(0, 8) }}：共 {{ batch.count }} 个商品，已完成
              {{ progress.done }} 个。可以直接去草稿箱，任务在后台继续跑。
            </p>
            <el-progress :percentage="percent" :stroke-width="14" />
            <el-button style="margin-top: 12px" @click="$router.push('/drafts')">去草稿箱</el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const router = useRouter();
const route = useRoute();
const tab = ref(route.query.tab === "excel" ? "excel" : "single");
const loading = ref(false);
const files = ref([]);
const batchFiles = ref([]);
const batch = ref(null);
const progress = ref({ done: 0 });
const form = reactive({ sku: "", price: "", moq: "", note: "" });
const styles = ref([]);
const listingTemplates = ref([]);
const excelFile = ref([]);
const excelImages = ref([]);
const excel = reactive({
  style: "lingxing",
  listingTemplateId: "",
  createDrafts: false,
  loading: false,
  preview: null,
  mapping: {},
  batch: null,
});
const excelProgress = ref({ done: 0 });
let timer = null;
let excelTimer = null;

const currentStyle = computed(() => styles.value.find((item) => item.id === excel.style));
const mappingRows = computed(() => (excel.preview?.headers || []).map((header) => ({ header })));
const excelPercent = computed(() => {
  if (!excel.batch?.count) return 0;
  return Math.min(100, Math.round((excelProgress.value.done / excel.batch.count) * 100));
});

onMounted(async () => {
  try {
    styles.value = await api.excelStyles();
    listingTemplates.value = store.shopId ? await api.templates({ shop_id: store.shopId }) : [];
    onStyleChange();
  } catch (error) {
    ElMessage.error(error.message);
  }
});

function styleLabel(id) {
  return styles.value.find((item) => item.id === id)?.label || id;
}

function onStyleChange() {
  excel.createDrafts = Boolean(currentStyle.value?.create_drafts_default);
  excel.preview = null;
}

function downloadTemplate() {
  window.location.href = api.excelTemplateUrl(excel.style, excel.listingTemplateId);
}

async function previewExcel() {
  if (!excelFile.value[0]?.raw) {
    ElMessage.warning("先选一个表格");
    return;
  }
  const body = new FormData();
  body.append("style", excel.style);
  body.append("file", excelFile.value[0].raw);
  excel.loading = true;
  try {
    excel.preview = await api.excelPreview(body);
    excel.mapping = { ...(excel.preview.mapping || {}) };
    ElMessage.success(`探测到 ${excel.preview.row_count} 行`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    excel.loading = false;
  }
}

async function importExcel() {
  if (!excelFile.value[0]?.raw) return;
  const body = new FormData();
  body.append("style", excel.style);
  body.append("shop_id", store.shopId || "");
  body.append("mapping", JSON.stringify(excel.mapping));
  body.append("create_drafts", excel.createDrafts ? "true" : "false");
  body.append("listing_template_id", excel.listingTemplateId);
  body.append("file", excelFile.value[0].raw);
  excelImages.value.forEach((item) => item.raw && body.append("images", item.raw));
  excel.loading = true;
  try {
    excel.batch = await api.excelImport(body);
    excelProgress.value = { done: 0 };
    clearInterval(excelTimer);
    excelTimer = setInterval(pollExcel, 3000);
    ElMessage.success(`已接收 ${excel.batch.count} 行，后台在入库`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    excel.loading = false;
  }
}

async function pollExcel() {
  if (!excel.batch) return;
  try {
    excelProgress.value = await api.batchProgress(excel.batch.batch_id);
    if (excelProgress.value.done >= excel.batch.count) clearInterval(excelTimer);
  } catch {
    clearInterval(excelTimer);
  }
}

const percent = computed(() => {
  if (!batch.value?.count) return 0;
  return Math.min(100, Math.round((progress.value.done / batch.value.count) * 100));
});

onUnmounted(() => {
  clearInterval(timer);
  clearInterval(excelTimer);
});

async function submitOne() {
  if (!files.value.length) {
    ElMessage.warning("至少传一张图");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("sku", form.sku);
  body.append("price", form.price);
  body.append("moq", form.moq);
  body.append("note", form.note);
  files.value.forEach((item) => item.raw && body.append("files", item.raw));

  loading.value = true;
  try {
    const draft = await api.feed(body);
    ElMessage.success(`草稿已生成：${draft.category_name || "待定类目"}`);
    router.push(`/drafts/${draft.id}`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function submitBatch() {
  if (!batchFiles.value.length) {
    ElMessage.warning("先把图片拖进来");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("price", form.price);
  body.append("moq", form.moq);
  batchFiles.value.forEach((item) => item.raw && body.append("files", item.raw));

  loading.value = true;
  try {
    batch.value = await api.feedBatch(body);
    progress.value = { done: 0 };
    clearInterval(timer);
    timer = setInterval(poll, 3000);
    ElMessage.success(`已拆成 ${batch.value.count} 个商品，正在后台成稿`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function poll() {
  if (!batch.value) return;
  try {
    progress.value = await api.batchProgress(batch.value.batch_id);
    if (progress.value.done >= batch.value.count) clearInterval(timer);
  } catch {
    clearInterval(timer);
  }
}
</script>

<style scoped>
.style-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
