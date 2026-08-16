<template>
  <div class="page">
    <div class="page-head">
      <div>
        <p class="page-kicker">货盘</p>
        <h2>投料</h2>
        <p class="muted">先选你手头有什么。人只出图、价格、起订量；类目和标题由 AI 按官方规则补。</p>
      </div>
    </div>

    <el-alert
      v-if="!store.shopId"
      type="warning"
      show-icon
      :closable="false"
      title="先授权一个店铺"
      description="投料要用店铺 token 拉类目规则并上传图片银行。"
      style="margin-bottom: 14px"
    />

    <div class="path-grid">
      <div class="path-card" :class="{ 'is-active': tab === 'single' || tab === 'batch' }" @click="tab = 'single'">
        <small>路径 01</small>
        <b>有实拍图</b>
        <p class="muted">单条或按货号前缀批量。工厂最常见。</p>
      </div>
      <div class="path-card" :class="{ 'is-active': tab === 'ai' }" @click="tab = 'ai'">
        <small>路径 02</small>
        <b>没图，先出提示词</b>
        <p class="muted">按类目复制 6 条，自己生图后再投。</p>
      </div>
      <div class="path-card" :class="{ 'is-active': tab === 'excel' }" @click="tab = 'excel'">
        <small>路径 03</small>
        <b>已有 Excel</b>
        <p class="muted">领星 / 店小秘 / 马帮 / 官方类目表。</p>
      </div>
    </div>

    <el-tabs v-model="tab" class="feed-tabs">
      <el-tab-pane label="套图提示词" name="ai">
        <div class="card">
          <p class="muted" style="margin-bottom: 14px">
            只要提示词。按类目出国际站 6 张位（白底主图、尺寸、细节、场景、外箱、OEM），
            复制到你常用的生图模型。出图后再来「单条 / 批量」投料。
          </p>
          <el-form label-width="108px" style="max-width: 760px">
            <el-form-item label="类目模板">
              <el-select v-model="aiForm.familyId" placeholder="不选则按品名自动匹配" clearable style="width: 360px">
                <el-option
                  v-for="item in templates.families || []"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-select>
              <div class="muted">{{ currentFamily?.why || "文具、五金、电子、服装等各有一套槽位。" }}</div>
            </el-form-item>
            <el-form-item label="品名 / 货">
              <el-input v-model="aiForm.productName" placeholder="例如 colored pencil set / 油漆刷" />
            </el-form-item>
            <el-form-item label="补充">
              <el-input
                v-model="aiForm.note"
                type="textarea"
                :rows="2"
                placeholder="材质、色号、一盒几支、能否印 logo。写上后提示词会锁这些事实。"
              />
            </el-form-item>
            <el-button :loading="aiForm.planning" type="primary" @click="planStack">出 6 条提示词</el-button>
          </el-form>

          <div v-if="plan" class="stack">
            <p>
              套用「{{ plan.family.name }}」· {{ plan.family.alibaba_hint }}
            </p>
            <p class="muted">{{ plan.platform_note }}</p>
            <el-button style="margin: 10px 0" @click="copyAll">复制全部提示词</el-button>
            <div class="slot-grid">
              <div v-for="slot in plan.slots" :key="slot.id" class="slot-card">
                <div class="slot-head">
                  <b>{{ slot.index }}. {{ slot.name }}</b>
                  <el-tag size="small">{{ slot.layout }} {{ slot.layout_name }}</el-tag>
                </div>
                <p class="muted">买手看这张：{{ slot.buyer_job }}</p>
                <pre class="prompt-body">{{ slot.prompt }}</pre>
                <el-button size="small" @click="copyOne(slot)">复制这条</el-button>
              </div>
            </div>
            <p class="muted">出图后去「单条上品」或「批量上品」把图投进来，后面类目和标题仍由 AI 填。</p>
          </div>
        </div>
      </el-tab-pane>
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
            <el-form-item v-if="currentStyle?.needs_category" label="叶子类目 ID">
              <el-input v-model="excel.categoryId" placeholder="官方是先选类目再下表，例如 21111112" style="width: 320px" />
              <div class="muted">可从在线商品或草稿上抄。AI 按这个类目的官方 schema 补标题和属性。</div>
            </el-form-item>
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
      <el-tab-pane label="有实拍 · 单条" name="single">
        <div class="card">
          <div class="toolbar" style="margin-top: 0">
            <el-radio-group v-model="photoMode">
              <el-radio-button value="single">单条</el-radio-button>
              <el-radio-button value="batch">按货号批量</el-radio-button>
            </el-radio-group>
          </div>
          <div v-if="photoMode === 'single'">
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
          <div v-else>
          <p class="muted" style="margin-bottom: 14px">
            图片名以货号开头，<code>SKU-1001_1.jpg</code> 会自动归成同一个商品。
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
const tab = ref(route.query.tab === "excel" ? "excel" : route.query.tab === "ai" ? "ai" : route.query.tab === "batch" ? "single" : "single");
const photoMode = ref(route.query.tab === "batch" ? "batch" : "single");
const templates = ref({ families: [], sources: [] });
const plan = ref(null);
const aiForm = reactive({
  familyId: "",
  productName: "",
  note: "",
  planning: false,
});
const currentFamily = computed(() => (templates.value.families || []).find((item) => item.id === aiForm.familyId));
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
  style: route.query.style || "lingxing",
  listingTemplateId: "",
  categoryId: "",
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
    templates.value = await api.imageTemplates();
    onStyleChange();
  } catch (error) {
    ElMessage.error(error.message);
  }
});

async function planStack() {
  if (!aiForm.productName && !aiForm.note && !aiForm.familyId) {
    ElMessage.warning("先写品名，或选一个类目模板");
    return;
  }
  aiForm.planning = true;
  try {
    plan.value = await api.planImages({
      family_id: aiForm.familyId,
      product_name: aiForm.productName,
      note: aiForm.note,
    });
    aiForm.familyId = plan.value.family.id;
    ElMessage.success(`已套「${plan.value.family.name}」6 条提示词`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    aiForm.planning = false;
  }
}

async function copyText(text, ok) {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success(ok);
  } catch {
    ElMessage.error("复制失败，请手动选中");
  }
}

function copyOne(slot) {
  copyText(slot.prompt, `已复制「${slot.name}」`);
}

function copyAll() {
  const text = (plan.value?.slots || [])
    .map((slot) => `# ${slot.index}. ${slot.name}\n${slot.prompt}`)
    .join("\n\n");
  copyText(text, "6 条提示词已复制");
}

function styleLabel(id) {
  return styles.value.find((item) => item.id === id)?.label || id;
}

function onStyleChange() {
  excel.createDrafts = Boolean(currentStyle.value?.create_drafts_default);
  excel.preview = null;
}

function downloadTemplate() {
  window.location.href = api.excelTemplateUrl(excel.style, excel.listingTemplateId, {
    categoryId: excel.categoryId,
    shopId: store.shopId,
  });
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
  body.append("category_id", excel.categoryId);
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
.feed-tabs :deep(.el-tabs__header) {
  display: none;
}
.style-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.stack {
  margin-top: 22px;
}
.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
  margin: 14px 0;
}
.slot-card {
  border: 1px solid #e6e9ef;
  border-radius: 10px;
  padding: 12px;
  background: #fff;
}
.slot-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.prompt-body {
  white-space: pre-wrap;
  font-size: 11px;
  line-height: 1.45;
  max-height: 160px;
  overflow: auto;
  margin: 8px 0;
  color: #4b5563;
  background: #f4f6f9;
  padding: 8px;
  border-radius: 6px;
}
.stack a {
  margin-right: 10px;
}
</style>
