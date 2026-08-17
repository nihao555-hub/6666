<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>投料</h2>
        <p class="muted">你只出图、价格、起订量。其余由系统和 AI 补齐。</p>
      </div>
    </div>

    <el-alert
      v-if="!store.shopId"
      type="warning"
      show-icon
      :closable="false"
      title="先登录一个店铺"
      description="登录之后才能按这家店的规则成稿、把图传到店铺图库。"
      style="margin-bottom: 14px"
    />

    <div class="path-grid">
      <button class="path-card" :class="{ 'is-active': tab === 'single' }" @click="choose('single')">
        <small>最常见</small>
        <b>有实拍图</b>
        <p class="muted">单条或按货号批量。</p>
      </button>
      <button class="path-card" :class="{ 'is-active': tab === 'ai' }" @click="choose('ai')">
        <small>没图时</small>
        <b>平台生成套图</b>
        <p class="muted">写出品名，画 6 张再填价格。</p>
      </button>
      <button class="path-card" :class="{ 'is-active': tab === 'excel' }" @click="choose('excel')">
        <small>批量上品</small>
        <b>下载表格，填完传回</b>
        <p class="muted">一行一个商品，一张表写多少就是多少。</p>
      </button>
    </div>

    <!-- 有实拍 -->
    <template v-if="tab === 'single'">
      <FishboneSteps v-model="photoStep" :steps="photoSteps" :reached="photoReached" />

      <div v-if="photoStep === 0" class="step-panel">
        <h3>上传产品图</h3>
        <p class="muted">单条最多 6 张。批量时按货号命名，例如 SKU-1001_1.jpg，会自动归成同一个商品。</p>
        <div class="toolbar" style="margin-top: 14px">
          <el-radio-group v-model="photoMode">
            <el-radio-button value="single">单条</el-radio-button>
            <el-radio-button value="batch">按货号批量</el-radio-button>
          </el-radio-group>
        </div>
        <el-upload
          v-if="photoMode === 'single'"
          v-model:file-list="files"
          list-type="picture-card"
          :auto-upload="false"
          :limit="6"
          accept="image/*"
        >
          <span style="font-size: 22px">+</span>
        </el-upload>
        <el-upload
          v-else
          v-model:file-list="batchFiles"
          :auto-upload="false"
          multiple
          accept="image/*"
          drag
          style="width: 100%; margin-top: 8px"
        >
          <div style="padding: 26px 0">把整个文件夹的图拖进来</div>
        </el-upload>
        <div class="step-actions">
          <el-button type="primary" :disabled="!hasPhotos" @click="advancePhoto(1)">下一步，填价格</el-button>
        </div>
      </div>

      <div v-else-if="photoStep === 1" class="step-panel">
        <h3>填价格和起订量</h3>
        <p class="muted">这两项是红线，AI 不会代填。批量时整批共用同一个价和起订量。</p>
        <div class="prop-form" style="margin-top: 8px">
          <div v-if="photoMode === 'single'" class="prop-row">
            <label>货号</label>
            <el-input v-model="form.sku" placeholder="留空则用图片文件名" />
          </div>
          <div class="prop-row">
            <label>单价</label>
            <el-input v-model="form.price" placeholder="12.50">
              <template #append>USD</template>
            </el-input>
          </div>
          <div class="prop-row">
            <label>起订量</label>
            <el-input v-model="form.moq" placeholder="100" />
          </div>
          <div v-if="photoMode === 'single'" class="prop-row">
            <label>补充</label>
            <el-input v-model="form.note" type="textarea" :rows="2" placeholder="可选。中文也行，例如：加厚款，可定制 logo" />
          </div>
        </div>
        <div class="step-actions">
          <el-button @click="photoStep = 0">上一步</el-button>
          <el-button type="primary" :disabled="!form.price || !form.moq" @click="advancePhoto(2)">下一步，生成草稿</el-button>
        </div>
      </div>

      <div v-else class="step-panel">
        <h3>生成草稿</h3>
        <p class="muted">系统会看图、定类目、对齐属性、写英文标题。大约 20～40 秒一条。</p>
        <div class="step-actions">
          <el-button @click="photoStep = 1">上一步</el-button>
          <el-button
            type="primary"
            :loading="loading"
            :disabled="!store.shopId"
            @click="photoMode === 'single' ? submitOne() : submitBatch()"
          >
            {{ photoMode === "single" ? "生成草稿" : "开始批量成稿" }}
          </el-button>
          <span v-if="loading" class="muted">正在成稿，可以先去干别的</span>
        </div>
        <div v-if="batch" style="margin-top: 18px">
          <p>共 {{ batch.count }} 个商品，已完成 {{ progress.done }} 个。关掉页面也不影响。</p>
          <el-progress :percentage="percent" :stroke-width="10" />
          <el-button style="margin-top: 12px" @click="$router.push('/drafts')">去草稿箱</el-button>
        </div>
      </div>
    </template>

    <!-- 没图：平台生成套图 -->
    <template v-else-if="tab === 'ai'">
      <FishboneSteps v-model="aiStep" :steps="aiSteps" :reached="aiReached" />

      <div v-if="aiStep === 0" class="step-panel">
        <h3>写出品名</h3>
        <p class="muted">没有实拍时，平台按国际站 6 个坑位画套图：白底主图、尺寸、细节、场景、外箱、OEM。生成图不是实拍。</p>
        <el-form label-width="88px" style="max-width: 720px; margin-top: 12px">
          <el-form-item label="类目">
            <div>
              <el-button @click="openAiCategory">{{ aiForm.categoryName || "选择国际站类目" }}</el-button>
              <p class="muted" style="margin: 6px 0 0">从这家店的官方类目树选到可发布的叶子。不选也能先出图。</p>
            </div>
          </el-form-item>
          <el-form-item label="出图风格">
            <div>
              <div class="family-chips">
                <button
                  v-for="item in templates.families || []"
                  :key="item.id"
                  type="button"
                  class="family-chip"
                  :class="{ 'is-active': aiForm.familyId === item.id }"
                  @click="aiForm.familyId = aiForm.familyId === item.id ? '' : item.id"
                >
                  {{ item.name }}
                </button>
              </div>
              <p class="muted" style="margin: 6px 0 0">可不选。不选则按官方类目和品名自动匹配。</p>
            </div>
          </el-form-item>
          <el-form-item label="品名">
            <el-input v-model="aiForm.productName" placeholder="例如 油漆刷 / colored pencil set" />
          </el-form-item>
          <el-form-item label="补充">
            <el-input v-model="aiForm.note" type="textarea" :rows="2" placeholder="材质、色号、一盒几支、能否印 logo" />
          </el-form-item>
        </el-form>
        <div class="step-actions">
          <el-button type="primary" :loading="aiForm.planning" @click="startGenerate">生成套图</el-button>
        </div>
      </div>

      <div v-else-if="aiStep === 1" class="step-panel">
        <h3>{{ imageJob?.status === "succeeded" ? "套图已画好" : "正在出图" }}</h3>
        <p class="muted">
          套用「{{ imageJob?.family?.name || "类目模板" }}」。{{ imageJob?.progress || "排队出图" }}
          这 6 张是平台生成图，不是实拍。
        </p>
        <el-progress :percentage="imagePercent" :stroke-width="10" style="margin: 14px 0" />
        <div class="slot-grid">
          <div v-for="slot in imageJob?.slots || []" :key="slot.id" class="slot-card">
            <div class="slot-photo">
              <img v-if="slot.url" :src="slot.url" :alt="slot.name" />
              <span v-else class="muted">{{ slot.status === "running" ? "正在画" : "排队" }}</span>
            </div>
            <div class="slot-head">
              <b>{{ slot.index }}. {{ slot.name }}</b>
            </div>
            <p class="muted">买手看这张：{{ slot.buyer_job }}</p>
          </div>
        </div>
        <el-alert
          v-if="imageJob?.status === 'failed'"
          type="error"
          :title="imageJob.error || '出图失败，请再试一次'"
          :closable="false"
          style="margin-bottom: 12px"
        />
        <div class="step-actions">
          <el-button @click="aiStep = 0">上一步</el-button>
          <el-button v-if="imageJob?.status === 'failed'" @click="startGenerate">再画一次</el-button>
          <el-button type="primary" :disabled="imageJob?.status !== 'succeeded'" @click="advanceAi(2)">
            下一步，填价格
          </el-button>
        </div>
      </div>

      <div v-else-if="aiStep === 2" class="step-panel">
        <h3>填价格和起订量</h3>
        <p class="muted">这两项是红线，AI 不会代填。</p>
        <div class="prop-form" style="margin-top: 8px">
          <div class="prop-row">
            <label>货号</label>
            <el-input v-model="form.sku" placeholder="留空则用品名" />
          </div>
          <div class="prop-row">
            <label>单价</label>
            <el-input v-model="form.price" placeholder="12.50">
              <template #append>USD</template>
            </el-input>
          </div>
          <div class="prop-row">
            <label>起订量</label>
            <el-input v-model="form.moq" placeholder="100" />
          </div>
          <div class="prop-row">
            <label>补充</label>
            <el-input v-model="form.note" type="textarea" :rows="2" placeholder="可选。中文也行" />
          </div>
        </div>
        <div class="step-actions">
          <el-button @click="aiStep = 1">上一步</el-button>
          <el-button type="primary" :disabled="!form.price || !form.moq" @click="advanceAi(3)">下一步，生成草稿</el-button>
        </div>
      </div>

      <div v-else class="step-panel">
        <h3>生成草稿</h3>
        <p class="muted">用刚画好的 6 张图成稿。大约 20～40 秒。草稿里会标黄：这不是实拍。</p>
        <div class="step-actions">
          <el-button @click="aiStep = 2">上一步</el-button>
          <el-button type="primary" :loading="loading" :disabled="!store.shopId || imageJob?.status !== 'succeeded'" @click="submitGenerated">
            生成草稿
          </el-button>
        </div>
      </div>
    </template>

    <!-- 表格批量 -->
    <template v-else>
      <FishboneSteps v-model="excelStep" :steps="excelSteps" :reached="excelReached" />

      <div v-if="excelStep === 0" class="step-panel">
        <h3>这批货是哪一类</h3>
        <p class="muted">整表共用一个类目。选错后面属性全废，所以这一步要人点一下，不能交给 AI。</p>
        <div style="margin-top: 16px">
          <el-button @click="openCategory">{{ sheetPlan.category_name || "选择类目" }}</el-button>
          <p v-if="sheetPlan.ai_attrs?.length" class="muted" style="margin-top: 10px">
            选好后，标题、关键词和 {{ sheetPlan.ai_attrs.map((item) => item.header).join("、") }} 都由 AI 补。
          </p>
        </div>
        <div class="step-actions">
          <el-button type="primary" :disabled="!excel.categoryId" @click="advanceExcel(1)">下一步，下载表格</el-button>
        </div>
      </div>

      <div v-else-if="excelStep === 1" class="step-panel">
        <h3>下载填写表</h3>
        <p class="muted">
          这张表的列是平台定的短表（货号、单价、起订量、图片、品牌、品名、备注），不是阿里后台下载的 40 列。
          上面选的官方类目只用来让 AI 按该叶子的发布规则补标题和属性，那些列不写进表。
        </p>
        <div class="sheet-preview" v-if="previewColumns.length">
          <table>
            <thead>
              <tr>
                <th v-for="col in previewColumns" :key="col.id">
                  {{ col.label }}<span v-if="col.required" class="need">必填</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr class="is-sample">
                <td v-for="col in previewColumns" :key="col.id">{{ col.example || "—" }}</td>
              </tr>
              <tr>
                <td v-for="col in previewColumns" :key="`${col.id}-empty`">
                  <span class="muted">{{ col.id === "sku" ? "从这行开始写你的货" : "" }}</span>
                </td>
              </tr>
            </tbody>
          </table>
          <p class="muted" style="margin-top: 8px">灰色那行是示例，导入时自动跳过。一行一个商品，往下接着写。</p>
        </div>
        <div class="policy-grid" style="margin-top: 16px">
          <section class="policy-card">
            <small>你填</small>
            <b>就这几列</b>
            <ul>
              <li v-for="item in policy.user_fills" :key="item.id">
                {{ item.label }}<span v-if="!item.required" class="muted"> 选填</span>
              </li>
            </ul>
          </section>
          <section class="policy-card">
            <small>AI 填</small>
            <b>不要写进表</b>
            <ul>
              <li v-for="item in policy.ai_fills" :key="item.id">{{ item.label }}</li>
            </ul>
          </section>
          <section class="policy-card is-redline">
            <small>红线</small>
            <b>不准交给 AI</b>
            <ul>
              <li v-for="item in policy.redline" :key="item.id">
                <strong>{{ item.label }}</strong>
              </li>
            </ul>
          </section>
        </div>
        <div class="step-actions">
          <el-button @click="excelStep = 0">上一步</el-button>
          <el-button type="primary" @click="downloadAndAdvance">下载填写表</el-button>
        </div>
      </div>

      <div v-else-if="excelStep === 2" class="step-panel">
        <h3>填完传回来</h3>
        <p class="muted">灰色那行是示例，导入时会自动跳过。从下一行开始写你的货。</p>
        <el-upload
          v-model:file-list="excelFile"
          :auto-upload="false"
          :limit="1"
          accept=".xlsx,.xlsm,.xls"
          drag
          style="margin-top: 14px"
          @change="onExcelPicked"
        >
          <div style="padding: 22px 0">把填好的表格拖到这里</div>
        </el-upload>
        <el-alert
          v-for="warning in excel.preview?.warnings || []"
          :key="warning"
          type="warning"
          :title="warning"
          :closable="false"
          style="margin: 12px 0 0"
        />
        <div v-if="excel.preview?.row_issues?.length" class="row-issues">
          <b>成稿前先看这几行</b>
          <p class="muted">红的要改完再传。黄的只是提醒。</p>
          <ul>
            <li v-for="(issue, index) in excel.preview.row_issues.slice(0, 12)" :key="index">
              <span :class="['dot', issue.level]"></span>
              第 {{ issue.line }} 行 {{ issue.sku }}：{{ issue.message }}
            </li>
          </ul>
        </div>
        <p v-if="excel.preview" class="muted" style="margin-top: 12px">
          识别到 {{ excel.preview.row_count }} 个商品，其中 {{ excel.preview.ready_count }} 个可以直接成稿。
        </p>
        <div class="step-actions">
          <el-button @click="excelStep = 1">上一步</el-button>
          <el-button type="primary" :disabled="!excelFile.length" @click="advanceExcel(3)">下一步，配上图片</el-button>
        </div>
      </div>

      <div v-else-if="excelStep === 3" class="step-panel">
        <h3>配上图片</h3>
        <p class="muted">表里写了链接就不用再传。本地图按货号命名，例如 SKU-1001_1.jpg。</p>
        <el-upload v-model:file-list="excelImages" :auto-upload="false" multiple accept="image/*" drag style="margin-top: 14px">
          <div style="padding: 22px 0">把图拖进来，或跳过这一步（表里已有链接）</div>
        </el-upload>
        <div class="step-actions">
          <el-button @click="excelStep = 2">上一步</el-button>
          <el-button type="primary" @click="advanceExcel(4)">下一步，开始成稿</el-button>
        </div>
      </div>

      <div v-else class="step-panel">
        <h3>开始成稿</h3>
        <p class="muted">后台一条一条过。关掉页面也不影响，去草稿箱只审红黄项即可。</p>
        <div class="step-actions">
          <el-button @click="excelStep = 3">上一步</el-button>
          <el-button
            type="primary"
            :loading="excel.loading"
            :disabled="!excelFile.length || !store.shopId || !excel.categoryId"
            @click="importSimple"
          >
            批量成稿
          </el-button>
        </div>
        <div v-if="excel.batch" style="margin-top: 18px">
          <p>共 {{ excel.batch.count }} 个商品，已成稿 {{ excelProgress.done }} 个。</p>
          <el-progress :percentage="excelPercent" :stroke-width="10" />
          <el-button style="margin-top: 12px" @click="$router.push('/drafts')">去草稿箱审红黄项</el-button>
        </div>
      </div>

      <details class="erp-more">
        <summary>已有领星 / 店小秘 / 马帮的现成表</summary>
        <el-radio-group v-model="excel.style" class="style-grid" @change="onStyleChange">
          <el-radio-button v-for="item in otherStyles" :key="item.id" :value="item.id">
            {{ item.label }}
          </el-radio-button>
        </el-radio-group>
        <p class="muted" style="margin: 12px 0 16px">{{ currentStyle?.summary }}</p>
        <el-form label-width="88px" style="max-width: 640px">
          <el-form-item v-if="currentStyle?.needs_listing_template" label="刊登模板">
            <el-select v-model="excel.listingTemplateId" placeholder="先选一个类目模板" style="width: 320px">
              <el-option
                v-for="item in listingTemplates"
                :key="item.id"
                :label="item.name"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="模板">
            <el-button @click="downloadTemplate">下载 {{ currentStyle?.label || "" }} 模板</el-button>
          </el-form-item>
          <el-form-item label="填好的表">
            <el-upload v-model:file-list="excelFile" :auto-upload="false" :limit="1" accept=".xlsx,.xlsm,.xls">
              <el-button>选择表格</el-button>
            </el-upload>
          </el-form-item>
          <el-form-item label="配套图片">
            <el-upload v-model:file-list="excelImages" :auto-upload="false" multiple accept="image/*">
              <el-button>选择图片</el-button>
            </el-upload>
          </el-form-item>
          <el-button :loading="excel.loading" :disabled="!excelFile.length" @click="previewExcel">探测表头</el-button>
          <el-button type="primary" :loading="excel.loading" :disabled="!excel.preview" @click="importExcel">
            确认导入
          </el-button>
        </el-form>
        <el-table v-if="excel.style !== 'simple' && excel.preview" :data="mappingRows" size="small" style="max-width: 640px; margin-top: 12px">
          <el-table-column prop="header" label="表格列" />
          <el-table-column label="对到">
            <template #default="{ row }">
              <el-select v-model="excel.mapping[row.header]" clearable placeholder="忽略这一列">
                <el-option v-for="field in excel.preview.fields" :key="field.id" :label="field.label" :value="field.id" />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
      </details>
    </template>

    <CategoryPicker v-model="categoryBrowser" @pick="pickCategory" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import CategoryPicker from "../components/CategoryPicker.vue";
import FishboneSteps from "../components/FishboneSteps.vue";
import { api } from "../api";
import { store } from "../store";

const router = useRouter();
const route = useRoute();
const tab = ref(route.query.tab === "excel" ? "excel" : route.query.tab === "ai" ? "ai" : "single");
const photoMode = ref(route.query.tab === "batch" ? "batch" : "single");
const photoStep = ref(0);
const photoReached = ref(0);
const aiStep = ref(0);
const aiReached = ref(0);
const excelStep = ref(0);
const excelReached = ref(0);

const photoSteps = [
  { key: "photos", label: "上传图片" },
  { key: "price", label: "填价格" },
  { key: "draft", label: "生成草稿" },
];
const aiSteps = [
  { key: "name", label: "写出品名" },
  { key: "draw", label: "生成套图" },
  { key: "price", label: "填价格" },
  { key: "draft", label: "生成草稿" },
];
const excelSteps = [
  { key: "cat", label: "选类目" },
  { key: "dl", label: "下载表格" },
  { key: "up", label: "传回表格" },
  { key: "img", label: "配上图片" },
  { key: "go", label: "开始成稿" },
];

const templates = ref({ families: [], sources: [] });
const imageJob = ref(null);
const aiForm = reactive({
  familyId: "",
  productName: "",
  note: "",
  planning: false,
  categoryId: "",
  categoryName: "",
});
const categoryTarget = ref("excel");
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
  style: route.query.style || "simple",
  listingTemplateId: "",
  categoryId: route.query.category || "",
  createDrafts: true,
  loading: false,
  preview: null,
  mapping: {},
  batch: null,
});
const sheetPlan = ref({ user_fills: [], ai_fills: [], redline: [], ai_attrs: [], category_name: "", preview: null });
const categoryBrowser = ref(false);
const excelProgress = ref({ done: 0 });
let timer = null;
let excelTimer = null;
let imageTimer = null;

const currentStyle = computed(() => styles.value.find((item) => item.id === excel.style));
const otherStyles = computed(() => styles.value.filter((item) => item.id !== "simple"));
const policy = computed(() => ({
  user_fills: sheetPlan.value.user_fills?.length ? sheetPlan.value.user_fills : currentStyle.value?.policy?.user_fills || [],
  ai_fills: sheetPlan.value.ai_fills?.length ? sheetPlan.value.ai_fills : currentStyle.value?.policy?.ai_fills || [],
  redline: sheetPlan.value.redline?.length ? sheetPlan.value.redline : currentStyle.value?.policy?.redline || [],
}));
const previewColumns = computed(() => sheetPlan.value.preview?.columns || policy.value.user_fills.map((item) => ({
  id: item.id,
  label: item.label,
  required: item.required,
  example: "",
})));
const mappingRows = computed(() => (excel.preview?.headers || []).map((header) => ({ header })));
const excelPercent = computed(() => {
  if (!excel.batch?.count) return 0;
  return Math.min(100, Math.round((excelProgress.value.done / excel.batch.count) * 100));
});
const percent = computed(() => {
  if (!batch.value?.count) return 0;
  return Math.min(100, Math.round((progress.value.done / batch.value.count) * 100));
});
const hasPhotos = computed(() => (photoMode.value === "single" ? files.value.length : batchFiles.value.length));
const imagePercent = computed(() => {
  const total = imageJob.value?.total || 6;
  return Math.min(100, Math.round(((imageJob.value?.done || 0) / total) * 100));
});

function choose(next) {
  tab.value = next;
}

function advancePhoto(index) {
  photoReached.value = Math.max(photoReached.value, index);
  photoStep.value = index;
}

function advanceExcel(index) {
  excelReached.value = Math.max(excelReached.value, index);
  excelStep.value = index;
}

function advanceAi(index) {
  aiReached.value = Math.max(aiReached.value, index);
  aiStep.value = index;
}

onMounted(async () => {
  try {
    templates.value = await api.imageTemplates();
  } catch (error) {
    ElMessage.error(error.message);
  }
  try {
    styles.value = await api.excelStyles();
    listingTemplates.value = store.shopId ? await api.templates({ shop_id: store.shopId }) : [];
    onStyleChange();
    await loadSheetPlan();
    if (excel.categoryId) excelReached.value = Math.max(excelReached.value, 1);
  } catch (error) {
    ElMessage.error(error.message);
  }
});

async function startGenerate() {
  if (!aiForm.productName && !aiForm.note && !aiForm.familyId) {
    ElMessage.warning("先写品名，或选一个类目");
    return;
  }
  aiForm.planning = true;
  try {
    imageJob.value = await api.generateImages({
      family_id: aiForm.familyId,
      product_name: aiForm.productName,
      note: aiForm.note,
      category_id: aiForm.categoryId,
      category_hint: aiForm.categoryName,
    });
    if (imageJob.value?.family?.id) aiForm.familyId = imageJob.value.family.id;
    advanceAi(1);
    clearInterval(imageTimer);
    imageTimer = setInterval(pollImageJob, 2000);
    await pollImageJob();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    aiForm.planning = false;
  }
}

async function pollImageJob() {
  if (!imageJob.value?.id) return;
  try {
    imageJob.value = await api.imageJob(imageJob.value.id);
    if (imageJob.value.status === "succeeded") {
      clearInterval(imageTimer);
      aiReached.value = Math.max(aiReached.value, 2);
      ElMessage.success("6 张套图已画好");
    } else if (imageJob.value.status === "failed") {
      clearInterval(imageTimer);
      ElMessage.error(imageJob.value.error || "出图失败，请再试一次");
    }
  } catch (error) {
    clearInterval(imageTimer);
    ElMessage.error(error.message);
  }
}

async function submitGenerated() {
  if (!imageJob.value?.id) {
    ElMessage.warning("先生成套图");
    return;
  }
  loading.value = true;
  try {
    const draft = await api.feedFromGenerated({
      shop_id: store.shopId,
      job_id: imageJob.value.id,
      sku: form.sku,
      price: form.price,
      moq: form.moq,
      note: form.note,
      category_id: aiForm.categoryId || imageJob.value.category_id || "",
    });
    ElMessage.success(`草稿已生成：${draft.category_name || "待定类目"}`);
    router.push(`/drafts/${draft.id}`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function onStyleChange() {
  excel.createDrafts = Boolean(currentStyle.value?.create_drafts_default);
  excel.preview = null;
}

async function onExcelPicked() {
  if (excel.style === "simple" && excelFile.value[0]?.raw) {
    await previewExcel();
  }
}

async function importSimple() {
  excel.createDrafts = true;
  if (!excel.preview) await previewExcel();
  if (excel.preview) await importExcel();
}

async function loadSheetPlan() {
  sheetPlan.value = await api.excelSheetPlan({
    shop_id: store.shopId || "",
    category_id: excel.categoryId || "",
  });
}

function openCategory() {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  categoryTarget.value = "excel";
  categoryBrowser.value = true;
}

function openAiCategory() {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  categoryTarget.value = "ai";
  categoryBrowser.value = true;
}

async function pickCategory(node) {
  if (categoryTarget.value === "ai") {
    aiForm.categoryId = node.category_id;
    aiForm.categoryName = node.label || node.name || node.cn_name || "";
    try {
      const planned = await api.planImages({
        product_name: aiForm.productName,
        category_hint: aiForm.categoryName,
        note: aiForm.note,
      });
      aiForm.familyId = planned.family?.id || "";
      ElMessage.success(`已选「${aiForm.categoryName}」，出图按「${planned.family?.name || "通用"}」`);
    } catch {
      ElMessage.success(`已选「${aiForm.categoryName}」`);
    }
    return;
  }
  excel.categoryId = node.category_id;
  try {
    await loadSheetPlan();
    ElMessage.success(`已选「${sheetPlan.value.category_name || node.label}」`);
    advanceExcel(1);
  } catch (error) {
    ElMessage.error(error.message);
  }
}

function downloadTemplate() {
  window.location.href = api.excelTemplateUrl(excel.style, excel.listingTemplateId, {
    categoryId: excel.categoryId,
    shopId: store.shopId,
  });
}

function downloadAndAdvance() {
  downloadTemplate();
  advanceExcel(2);
}

async function previewExcel() {
  if (!excelFile.value[0]?.raw) {
    ElMessage.warning("先选一个表格");
    return;
  }
  const body = new FormData();
  body.append("style", excel.style);
  body.append("shop_id", store.shopId || "");
  body.append("category_id", excel.categoryId || "");
  body.append("file", excelFile.value[0].raw);
  excel.loading = true;
  try {
    excel.preview = await api.excelPreview(body);
    excel.mapping = { ...(excel.preview.mapping || {}) };
    ElMessage.success(`识别到 ${excel.preview.row_count} 个商品`);
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
    ElMessage.success(`已接收 ${excel.batch.count} 个商品，后台在成稿`);
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

onUnmounted(() => {
  clearInterval(timer);
  clearInterval(excelTimer);
  clearInterval(imageTimer);
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
.path-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 18px;
}
.path-card {
  text-align: left;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: var(--radius);
  padding: 12px 14px;
  cursor: pointer;
  font-family: inherit;
  color: inherit;
  transition: background 0.1s ease, border-color 0.1s ease;
}
.path-card:hover {
  background: var(--gray2);
}
.path-card.is-active {
  background: var(--accent-wash);
  border-color: var(--accent-line);
}
.path-card small {
  display: block;
  color: var(--muted);
  margin-bottom: 4px;
  font-size: 11px;
  font-weight: 600;
}
.path-card b {
  display: block;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 2px;
}
.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
  margin: 14px 0;
}
.slot-card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px;
}
.slot-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin: 8px 0 4px;
}
.slot-photo {
  aspect-ratio: 1;
  border-radius: var(--radius-sm);
  background: var(--gray3);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.slot-photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.family-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.family-chip {
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 999px;
  padding: 4px 10px;
  font: inherit;
  font-size: 12px;
  color: inherit;
  cursor: pointer;
}
.family-chip.is-active {
  background: var(--accent-wash);
  border-color: var(--accent-line);
}
.erp-more {
  margin-top: 22px;
  color: var(--muted);
  font-size: 13px;
}
.erp-more summary {
  cursor: pointer;
  margin-bottom: 12px;
}
.style-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.row-issues {
  margin-top: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px 14px;
  background: var(--gray3);
}
.row-issues ul {
  margin: 8px 0 0;
  padding-left: 4px;
  list-style: none;
  color: var(--ink-2);
}
.row-issues li + li {
  margin-top: 4px;
}
.policy-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.policy-card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--gray3);
  padding: 12px 14px;
}
.policy-card.is-redline {
  background: var(--red-soft);
  border-color: var(--red-line);
}
.policy-card small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
}
.policy-card b {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
}
.policy-card ul {
  margin: 0;
  padding-left: 16px;
  color: var(--ink-2);
}
.policy-card li + li {
  margin-top: 4px;
}
.sheet-preview {
  margin-top: 16px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius);
}
.sheet-preview table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.sheet-preview th,
.sheet-preview td {
  padding: 8px 10px;
  border-right: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}
.sheet-preview th {
  background: var(--ink);
  color: #fff;
  font-weight: 600;
}
.sheet-preview .need {
  margin-left: 6px;
  font-size: 10px;
  font-weight: 500;
  color: #ffcdce;
}
.sheet-preview tr.is-sample td {
  color: var(--muted);
  font-style: italic;
  background: var(--gray3);
}
@media (max-width: 900px) {
  .path-grid,
  .policy-grid {
    grid-template-columns: 1fr;
  }
}
</style>
