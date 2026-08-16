<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>投料上品</h2>
        <p class="muted">
          图也可以 AI 按类目高转化模板生成：白底主图、尺寸、细节、场景、外箱、OEM。
          有实拍就当参考图锁外形；没有实拍就选类目套图。价格和起订量仍要你定。
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
      <el-tab-pane label="AI 套图" name="ai">
        <div class="card">
          <p class="muted" style="margin-bottom: 14px">
            国际站图片银行最多 6 张。我们按类目套高转化槽位，不套亚马逊那套零售对比图。
            主图强制白底无字；最后两张给外箱和定制，这是批发询盘真正看的。
          </p>
          <el-alert
            v-if="templates.image_enabled === false"
            type="warning"
            :closable="false"
            show-icon
            title="现在只能出套图提示词"
            description="配好 IMAGE_MODEL 后才能一键生图。提示词仍可复制给别的生图工具。"
            style="margin-bottom: 14px"
          />
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
                placeholder="材质、色号、一盒几支、能否印 logo。没有实拍时这些决定像不像你们的货。"
              />
            </el-form-item>
            <el-form-item label="参考实拍">
              <el-upload v-model:file-list="aiRefs" list-type="picture-card" :auto-upload="false" :limit="4" accept="image/*">
                <span style="font-size: 22px">+</span>
              </el-upload>
              <div class="muted">可选。有实拍会锁外形，避免生成另一款货。</div>
            </el-form-item>
            <el-button :loading="aiForm.planning" @click="planStack">生成 6 张位方案</el-button>
          </el-form>

          <div v-if="plan" class="stack">
            <p>
              套用「{{ plan.family.name }}」· {{ plan.family.alibaba_hint }}
            </p>
            <p class="muted">{{ plan.platform_note }}</p>
            <div class="slot-grid">
              <div v-for="slot in plan.slots" :key="slot.id" class="slot-card">
                <div class="slot-head">
                  <b>{{ slot.index }}. {{ slot.name }}</b>
                  <el-tag size="small">{{ slot.layout }} {{ slot.layout_name }}</el-tag>
                </div>
                <p class="muted">买手看这张：{{ slot.buyer_job }}</p>
                <img v-if="generated[slot.id]" :src="generated[slot.id].url" :alt="slot.name" class="slot-img" />
                <el-button
                  size="small"
                  type="primary"
                  :loading="aiForm.generating === slot.id"
                  :disabled="!templates.image_enabled"
                  @click="generateOne(slot)"
                >
                  {{ generated[slot.id] ? "重生成" : "生成这张" }}
                </el-button>
                <details class="prompt">
                  <summary>提示词</summary>
                  <pre>{{ slot.prompt }}</pre>
                </details>
              </div>
            </div>
            <el-button :disabled="!templates.image_enabled" :loading="aiForm.generating === 'all'" @click="generateAll">
              按模板生成全部 6 张
            </el-button>
            <p v-if="plan.sources?.length" class="muted" style="margin-top: 12px">
              槽位方法参考：
              <a v-for="item in plan.sources" :key="item.repo" :href="item.url" target="_blank" rel="noreferrer">
                {{ item.repo }}
              </a>
            </p>
          </div>

          <el-divider v-if="generatedCount" />
          <el-form v-if="generatedCount" label-width="108px" style="max-width: 620px">
            <el-form-item label="货号">
              <el-input v-model="form.sku" placeholder="留空则用主图文件名" />
            </el-form-item>
            <el-form-item label="单价">
              <el-input v-model="form.price" placeholder="12.50">
                <template #append>USD</template>
              </el-input>
            </el-form-item>
            <el-form-item label="起订量">
              <el-input v-model="form.moq" placeholder="100" />
            </el-form-item>
            <el-button type="primary" :loading="loading" :disabled="!store.shopId" @click="submitGenerated">
              用这套图生成草稿
            </el-button>
          </el-form>
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
const tab = ref(route.query.tab === "excel" ? "excel" : route.query.tab === "ai" ? "ai" : "single");
const templates = ref({ families: [], image_enabled: false, sources: [] });
const aiRefs = ref([]);
const plan = ref(null);
const generated = ref({});
const aiForm = reactive({
  familyId: "",
  productName: "",
  note: "",
  planning: false,
  generating: "",
});
const currentFamily = computed(() => (templates.value.families || []).find((item) => item.id === aiForm.familyId));
const generatedCount = computed(() => Object.keys(generated.value).length);
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
    generated.value = {};
    ElMessage.success(`已套「${plan.value.family.name}」6 张位`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    aiForm.planning = false;
  }
}

async function generateOne(slot) {
  const body = new FormData();
  body.append("slot_id", slot.id);
  body.append("prompt", slot.prompt);
  body.append("product_name", aiForm.productName);
  body.append("family_id", plan.value?.family?.id || "");
  aiRefs.value.forEach((item) => item.raw && body.append("references", item.raw));
  aiForm.generating = slot.id;
  try {
    const result = await api.generateImageSlot(body);
    generated.value = { ...generated.value, [slot.id]: result };
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    aiForm.generating = "";
  }
}

async function generateAll() {
  if (!plan.value?.slots?.length) return;
  aiForm.generating = "all";
  try {
    for (const slot of plan.value.slots) {
      aiForm.generating = slot.id;
      await generateOne(slot);
    }
    ElMessage.success(`已生成 ${Object.keys(generated.value).length} 张`);
  } finally {
    aiForm.generating = "";
  }
}

async function submitGenerated() {
  const slots = plan.value?.slots || [];
  const files = [];
  for (const slot of slots) {
    const item = generated.value[slot.id];
    if (!item) continue;
    const response = await fetch(item.url, { credentials: "include" });
    if (!response.ok) {
      ElMessage.error(`读取 ${slot.name} 失败`);
      return;
    }
    const blob = await response.blob();
    files.push(new File([blob], item.filename || `${slot.id}.png`, { type: "image/png" }));
  }
  if (!files.length) {
    ElMessage.warning("至少先生成一张图");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("sku", form.sku);
  body.append("price", form.price);
  body.append("moq", form.moq);
  body.append("note", aiForm.note || aiForm.productName);
  files.forEach((file) => body.append("files", file));
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
.slot-img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 8px;
  margin: 8px 0;
  background: #f4f6f9;
}
.prompt {
  margin-top: 8px;
  font-size: 12px;
  color: #8a94a6;
}
.prompt pre {
  white-space: pre-wrap;
  font-size: 11px;
  line-height: 1.45;
  max-height: 140px;
  overflow: auto;
}
.stack a {
  margin-right: 10px;
}
</style>
