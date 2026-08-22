<template>
  <div class="page">
    <div v-if="docStep !== 1" class="page-head">
      <div>
        <h2>批量上品</h2>
        <p class="muted">选类目 → 下载智能填写表 → 上传解析 → 审核出图成稿。做到一半会自动记下，关掉也能回来。</p>
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

    <div v-if="sessionBooting" class="boot-panel">
      <p class="muted">正在准备批量任务…</p>
    </div>

    <template v-else-if="sessionId">
      <div v-if="otherSessions.length" class="resume-inline">
        <span class="muted">其他进行中的任务：</span>
        <button
          v-for="item in otherSessions"
          :key="item.id"
          type="button"
          class="resume-chip"
          @click="resumeSession(item.id)"
        >
          {{ item.title }}
        </button>
      </div>

      <div v-if="docStep !== 1" class="flow-bar">
        <el-button @click="backToChooser">新建任务</el-button>
        <span class="muted">{{ currentTitle }} · 做到一半会自动记下，关掉也能回来</span>
        <el-button text @click="dropCurrent">不要这条了</el-button>
      </div>

      <FishboneSteps v-if="docStep !== 1" v-model="docStep" :steps="docSteps" :reached="docReached" />

      <div v-if="docStep === 0" class="step-panel">
        <h3>选类目，生成填写表</h3>
        <p class="muted">选好叶子类目后，AI 会分析需要填哪些列。</p>
        <div style="margin-top: 16px">
          <el-button type="primary" @click="openDocCategory">{{ doc.categoryName || smartPlan.category_name || "选择类目" }}</el-button>
        </div>

        <section v-if="smartPlanLoading" class="plan-panel plan-panel-loading">
          <section class="ai-timeline ai-timeline-vertical" aria-live="polite">
            <header class="ai-timeline-head">
              <strong>AI 正在分析类目</strong>
              <span class="ai-timeline-badge is-live">进行中</span>
            </header>
            <ol class="ai-timeline-track">
              <li
                v-for="(step, index) in smartPlanAiSteps"
                :key="step.id"
                class="ai-timeline-item"
                :class="`is-${step.status}`"
              >
                <div class="ai-timeline-rail" aria-hidden="true">
                  <span class="ai-timeline-dot" />
                  <span v-if="index < smartPlanAiSteps.length - 1" class="ai-timeline-line" />
                </div>
                <div class="ai-timeline-content">
                  <div class="ai-timeline-row">
                    <span class="ai-timeline-label">{{ step.label }}</span>
                    <span class="ai-timeline-status">{{ reviewStepStatusLabel(step.status) }}</span>
                  </div>
                  <p v-if="step.detail" class="ai-timeline-detail">{{ step.detail }}</p>
                </div>
              </li>
            </ol>
          </section>
        </section>

        <section v-else-if="doc.categoryId && smartPlan.column_count" class="plan-panel">
          <header class="plan-head">
            <h4>{{ smartPlan.category_name || doc.categoryName }}</h4>
            <span class="plan-badge">需填 {{ smartPlan.column_count }} 列</span>
          </header>
          <p v-if="smartPlan.reasoning" class="plan-reasoning">{{ smartPlan.reasoning }}</p>
          <div v-if="smartColumnLabels.length" class="plan-columns">
            <div class="plan-column-tags">
              <span v-for="label in smartColumnLabels" :key="label" class="plan-tag">{{ label }}</span>
            </div>
          </div>
          <p v-if="smartPlan.tips" class="plan-tips">{{ smartPlan.tips }}</p>
          <p v-if="smartPlan.cached" class="plan-cache-note muted">已使用上次规划结果，点「重新规划」才会再次调用 AI。</p>
        </section>
        <div class="toolbar" style="margin: 16px 0 12px">
          <el-button type="primary" :disabled="!doc.categoryId || smartPlanLoading || docTemplateDownloading" :loading="docTemplateDownloading" @click="downloadDocTemplate">
            下载智能填写表
          </el-button>
          <el-button :disabled="!doc.categoryId || smartPlanLoading" @click="refreshSmartPlan">重新规划</el-button>
        </div>
        <section v-if="doc.categoryId" class="image-help">
          <h4>上传表格和图片</h4>
          <p class="upload-flow-lead">不用改文件名。表格和图一起拖进来，系统按<strong>货号</strong>自动配对。</p>
          <ul class="upload-flow-steps upload-flow-simple">
            <li>文件名或文件夹名里<strong>包含货号</strong>即可，例如 <code>产品-A001.jpg</code>、<code>A001/1.png</code></li>
            <li>也可点「选图片文件夹」一次导入整个目录（支持子文件夹按货号分）</li>
            <li>填好表格后点「解析并进入审核」，AI 写文案并补图</li>
          </ul>
          <p v-if="uploadSummary" class="upload-summary">{{ uploadSummary }}</p>
        </section>
        <div
          class="upload-drop-zone"
          @dragover.prevent
          @dragenter.prevent
          @drop.prevent="onDropFiles"
        >
          <input ref="folderInput" type="file" webkitdirectory multiple accept="image/*" class="hidden-folder-input" @change="onFolderPick" />
          <el-upload
            v-model:file-list="docFiles"
            :auto-upload="false"
            multiple
            accept=".xlsx,.xls,.xlsm,.csv,.txt,.md,.jpg,.jpeg,.png,.webp,.pdf"
            drag
            @change="onDocFilesChange"
          >
            <div class="upload-drop-inner">
              <p>拖入填好的表格 + 商品图片</p>
              <p class="muted upload-drop-hint">文件名或文件夹名包含货号即可，不必改成 SKU-1001.jpg</p>
              <el-button type="primary" plain @click.stop="pickImageFolder">选图片文件夹</el-button>
            </div>
          </el-upload>
          <p v-if="!doc.categoryId" class="upload-note muted">可先上传文件；解析前仍需选择叶子类目。</p>
        </div>
        <div class="step-actions" style="margin-top: 16px">
          <el-button type="primary" :loading="docGrid.loading" :disabled="!doc.categoryId || !docFiles.some((item) => item.raw)" @click="parseDocuments">
            {{ parseStatus || "解析并进入审核" }}
          </el-button>
        </div>
      </div>

      <section
        v-if="showReviewAiTimeline"
        class="ai-timeline ai-timeline-vertical audit-ai-timeline"
        aria-live="polite"
      >
        <header class="ai-timeline-head">
          <strong>AI 审核助手</strong>
          <span v-if="docGrid.loading || reviewAssistRunning || hasPendingImageJobs()" class="ai-timeline-badge is-live">进行中</span>
          <span v-else-if="reviewAiAllDone" class="ai-timeline-badge is-done">已完成</span>
        </header>
        <ol class="ai-timeline-track">
          <li
            v-for="(step, index) in reviewAiSteps"
            :key="step.id"
            class="ai-timeline-item"
            :class="`is-${step.status}`"
          >
            <div class="ai-timeline-rail" aria-hidden="true">
              <span class="ai-timeline-dot" />
              <span v-if="index < reviewAiSteps.length - 1" class="ai-timeline-line" />
            </div>
            <div class="ai-timeline-content">
              <div class="ai-timeline-row">
                <span class="ai-timeline-label">{{ step.label }}</span>
                <span class="ai-timeline-status">{{ reviewStepStatusLabel(step.status) }}</span>
              </div>
              <p v-if="step.detail" class="ai-timeline-detail">{{ step.detail }}</p>
            </div>
          </li>
        </ol>
      </section>

      <section v-if="ecosystemBrief && doc.categoryId && docStep === 0" class="ecosystem-brief-panel ecosystem-brief-compact">
        <header class="ecosystem-brief-head">
          <strong>阿里生态助手</strong>
          <span class="ecosystem-brief-badge">国际站 · 询盘最大化</span>
        </header>
        <p v-if="ecosystemBrief.tips" class="ecosystem-brief-tips">{{ ecosystemBrief.tips }}</p>
        <ol v-if="ecosystemBrief.assistant_steps?.length" class="ecosystem-brief-steps">
          <li v-for="(step, idx) in ecosystemBrief.assistant_steps" :key="idx">{{ step }}</li>
        </ol>
        <div v-if="ecosystemBrief.golden_titles?.length" class="ecosystem-golden">
          <small>店里同品类在售标题（AI 参考结构与用词，不会照抄）</small>
          <p v-for="(title, idx) in ecosystemBrief.golden_titles.slice(0, 3)" :key="idx" class="golden-title">{{ title }}</p>
        </div>
        <div v-if="ecosystemBrief.keyword_strategy?.length" class="ecosystem-kw-tiers">
          <span
            v-for="item in ecosystemBrief.keyword_strategy"
            :key="item.tier"
            class="kw-tier"
            :class="`is-${String(item.tier || '').toLowerCase()}`"
            :title="item.hint"
          >
            {{ item.tier }} · {{ item.label }}
          </span>
        </div>
      </section>

      <div v-if="docStep === 1" class="step-panel audit-shell">
        <header class="audit-header">
          <button type="button" class="audit-back" @click="docStep = 0">← 返回</button>
          <h3>内容审核</h3>
          <p class="audit-subtitle">
            表格里每一列都会展示：Excel 原值 + AI 补全。按阿里国际站规则（合规→匹配→询盘）核对后标记通过。
          </p>
        </header>

        <section v-if="ecosystemBrief" class="ecosystem-brief-panel audit-ecosystem-panel">
          <header class="ecosystem-brief-head">
            <strong>阿里生态助手</strong>
            <span class="ecosystem-brief-badge">国际站 · 询盘最大化</span>
          </header>
          <p v-if="ecosystemBrief.tips" class="ecosystem-brief-tips">{{ ecosystemBrief.tips }}</p>
          <ol v-if="ecosystemBrief.assistant_steps?.length" class="ecosystem-brief-steps">
            <li v-for="(step, idx) in ecosystemBrief.assistant_steps" :key="idx">{{ step }}</li>
          </ol>
          <div v-if="ecosystemBrief.golden_titles?.length" class="ecosystem-golden">
            <small>店里同品类在售标题（AI 参考结构与用词，不会照抄）</small>
            <p v-for="(title, idx) in ecosystemBrief.golden_titles.slice(0, 3)" :key="idx" class="golden-title">{{ title }}</p>
          </div>
          <div v-if="ecosystemBrief.keyword_strategy?.length" class="ecosystem-kw-tiers">
            <span
              v-for="item in ecosystemBrief.keyword_strategy"
              :key="item.tier"
              class="kw-tier"
              :class="`is-${String(item.tier || '').toLowerCase()}`"
              :title="item.hint"
            >
              {{ item.tier }} · {{ item.label }}
            </span>
          </div>
        </section>

        <section class="audit-toolbar-card">
          <div class="audit-toolbar">
            <div class="audit-filters" role="tablist" aria-label="筛选商品">
              <button
                v-for="item in auditFilterOptions"
                :key="item.id"
                type="button"
                class="audit-filter-tab"
                :class="{ 'is-active': reviewFilter === item.id }"
                @click="reviewFilter = item.id; reviewPage = 1"
              >
                {{ item.label }}<small>{{ item.count }}</small>
              </button>
            </div>
            <div class="audit-toolbar-right">
              <el-input v-model="reviewSearch" clearable placeholder="搜索商品名称或关键词" class="audit-search" />
              <el-button plain disabled>筛选</el-button>
              <el-button plain :loading="docGrid.checking" @click="recheckDocGrid">刷新</el-button>
            </div>
          </div>
        </section>

        <section class="audit-field-legend">
          <span><i class="legend-dot is-required" />官方必填（红标列，缺了发不出）</span>
          <span><i class="legend-dot is-score" />选填加分（填齐更容易到 5.0 分）</span>
          <span class="muted">表格原值保留；AI 只补有依据的字段，价/量/品牌不会自动编</span>
        </section>

        <section class="audit-table-card">
          <div class="audit-table-scroll">
            <table class="audit-table doc-grid-wide">
              <thead>
                <tr>
                  <th class="col-check"><el-checkbox v-model="docGrid.selectAll" @change="toggleSelectAll" /></th>
                  <th class="col-row-num">#</th>
                  <th class="col-slots">商品图 ×6</th>
                  <th
                    v-for="col in docDataColumns"
                    :key="col.id"
                    class="col-field"
                    :class="auditColumnClass(col)"
                  >
                    {{ col.label }}<span v-if="col.required" class="need">必填</span>
                  </th>
                  <th class="col-status">状态</th>
                  <th class="col-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="view in paginatedDocRowViews"
                  :key="view.row.line || view.index"
                  :class="{
                    'is-issue': rowHasIssues(view.row),
                    'is-selected': view.row._selected,
                    'is-approved': rowAuditStatus(view.row) === 'approved',
                    'is-rejected': rowAuditStatus(view.row) === 'rejected',
                  }"
                >
                  <td class="col-check">
                    <el-checkbox v-model="view.row._selected" />
                  </td>
                  <td class="col-row-num">{{ view.index + 1 }}</td>
                  <td class="col-slots">
                    <div class="slot-strip">
                      <div
                        v-for="slot in rowSlots(view.row)"
                        :key="`${view.index}-${slot.index}`"
                        class="slot-thumb"
                        :class="`is-${slot.status || 'empty'}`"
                        :title="slot.name"
                      >
                        <img v-if="slot.url" :src="slot.url" :alt="slot.name" />
                        <span v-else>{{ slot.index }}</span>
                      </div>
                    </div>
                  </td>
                  <td
                    v-for="col in docDataColumns"
                    :key="`${view.index}-${col.id}`"
                    class="col-field"
                    :class="auditColumnClass(col)"
                  >
                    <el-select
                      v-if="col.options?.length"
                      v-model="view.row[col.id]"
                      filterable
                      clearable
                      :placeholder="col.required ? '请选择' : '选填'"
                      size="small"
                      style="width: 100%"
                    >
                      <el-option v-for="opt in col.options" :key="opt.value" :label="opt.label" :value="opt.label" />
                    </el-select>
                    <el-input
                      v-else-if="col.id === 'title' || col.id === 'note'"
                      v-model="view.row[col.id]"
                      type="textarea"
                      :rows="2"
                      size="small"
                      :placeholder="col.label"
                    />
                    <el-input v-else v-model="view.row[col.id]" size="small" :placeholder="col.label" />
                  </td>
                  <td class="col-status">
                    <span class="audit-status" :class="`is-${rowAuditStatus(view.row)}`">{{ rowStatusLabel(view.row) }}</span>
                  </td>
                  <td class="col-actions">
                    <div class="audit-row-actions">
                      <button type="button" class="audit-action is-approve" title="通过" @click="approveRow(view.row)">✓</button>
                      <button type="button" class="audit-action is-reject" title="不通过" @click="rejectRow(view.row)">✕</button>
                      <button type="button" class="audit-action is-view" title="查看详情" @click="openRowDetail(view)">👁</button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!paginatedDocRowViews.length">
                  <td :colspan="auditTableColSpan" class="review-empty">
                    暂无商品<el-button text @click="reviewFilter = 'all'; reviewSearch = ''">显示全部</el-button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <details v-if="docGrid.row_issues?.length" class="review-issues">
          <summary>
            <span>成稿前先看这几行（{{ docGrid.row_issues.length }}）</span>
          </summary>
          <ul>
            <li v-for="(issue, idx) in docGrid.row_issues.slice(0, 20)" :key="idx">
              第 {{ issue.line }} 行 {{ issue.sku }}：{{ issue.message }}
            </li>
          </ul>
        </details>

        <footer class="audit-footer">
          <div class="audit-footer-left">
            已选择 <b>{{ docSelectedCount }}</b> 项
          </div>
          <div class="audit-footer-center">
            <el-button @click="batchApprove">批量通过</el-button>
            <el-button @click="batchReject">批量不通过</el-button>
          </div>
          <div class="audit-footer-right">
            <el-pagination
              v-model:current-page="reviewPage"
              v-model:page-size="reviewPageSize"
              :total="filteredDocRowViews.length"
              :page-sizes="[10, 20, 50]"
              layout="total, prev, pager, next, sizes"
              size="small"
            />
            <el-button
              type="primary"
              :loading="docGrid.loading"
              :disabled="!docGrid.rows.length || !store.shopId || !doc.categoryId"
              @click="importDocRows"
            >
              批量成稿
            </el-button>
          </div>
        </footer>

        <div v-if="doc.batch" class="review-batch-progress">
          <p>成稿 {{ docProgress.done }}/{{ doc.batch.count }}</p>
          <el-progress :percentage="docPercent" :stroke-width="8" />
          <el-button v-if="docProgress.complete" type="primary" @click="goDocBatchDrafts('pending')">去审这一批</el-button>
        </div>

        <el-drawer v-model="rowDetailOpen" :title="rowDetailTitle" size="560px" destroy-on-close>
          <div v-if="rowDetailRow" class="audit-drawer">
            <div class="audit-drawer-section">
              <h4>全部字段</h4>
              <div v-for="col in docDataColumns" :key="col.id" class="audit-drawer-field">
                <label>
                  {{ col.label }}
                  <span v-if="col.required" class="need">必填</span>
                </label>
                <el-select
                  v-if="col.options?.length"
                  v-model="rowDetailRow[col.id]"
                  filterable
                  clearable
                  :placeholder="col.required ? '请选择' : '选填'"
                  style="width: 100%"
                >
                  <el-option v-for="opt in col.options" :key="opt.value" :label="opt.label" :value="opt.label" />
                </el-select>
                <el-input
                  v-else-if="col.id === 'title' || col.id === 'note'"
                  v-model="rowDetailRow[col.id]"
                  type="textarea"
                  :rows="2"
                />
                <el-input v-else v-model="rowDetailRow[col.id]" />
              </div>
            </div>
            <div class="audit-drawer-section">
              <h4>图片</h4>
              <div class="slot-strip">
                <div
                  v-for="slot in rowSlots(rowDetailRow)"
                  :key="slot.index"
                  class="slot-thumb"
                  :class="`is-${slot.status || 'empty'}`"
                >
                  <img v-if="slot.url" :src="slot.url" :alt="slot.name" />
                  <span v-else>{{ slot.index }}</span>
                </div>
              </div>
              <div class="audit-drawer-actions">
                <el-button type="primary" @click="approveRow(rowDetailRow); rowDetailOpen = false">通过</el-button>
                <el-button @click="rejectRow(rowDetailRow); rowDetailOpen = false">不通过</el-button>
              </div>
            </div>
          </div>
        </el-drawer>
      </div>
    </template>

    <CategoryPicker v-model="categoryBrowser" @pick="pickCategory" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { prefetchCategoryPicker } from "../categoryPickerCache";
import CategoryPicker from "../components/CategoryPicker.vue";
import FishboneSteps from "../components/FishboneSteps.vue";
import { buildUploadMap, fileStorageKey, matchUploadFiles } from "../imageMatch";
import { api } from "../api";
import { store } from "../store";

const router = useRouter();
const route = useRoute();
const DEAD_SESSIONS_KEY = "icbu-dead-feed-sessions";
const sessionId = ref("");
const deadSessionIds = loadDeadSessionIds();
const verifiedSessionIds = ref(new Set());
let sessionEnsurePromise = null;
let startPathPromise = null;
let persistInFlight = null;
let sessionGeneration = 0;
let persistBlockedUntil = 0;
const sessionApiRetryDelays = [250, 500, 900];
const sessionBooting = ref(true);
const openSessions = ref([]);
const currentTitle = ref("");
const restoring = ref(false);
const docStep = ref(0);
const docReached = ref(0);
const docSteps = [
  { key: "setup", label: "填写表下载上传" },
  { key: "grid", label: "审核出图成稿" },
];
const reviewFilter = ref("all");
const reviewSearch = ref("");
const reviewPage = ref(1);
const reviewPageSize = ref(10);
const rowDetailOpen = ref(false);
const rowDetailRow = ref(null);
const reviewImageInput = ref(null);
const docInferring = ref(false);
const parseStatus = ref("");
const DEFAULT_IMAGE_SLOTS = [
  { index: 1, id: "slot-1", name: "白底主图", status: "empty", url: "" },
  { index: 2, id: "slot-2", name: "细节", status: "empty", url: "" },
  { index: 3, id: "slot-3", name: "尺寸", status: "empty", url: "" },
  { index: 4, id: "slot-4", name: "场景", status: "empty", url: "" },
  { index: 5, id: "slot-5", name: "外箱", status: "empty", url: "" },
  { index: 6, id: "slot-6", name: "OEM", status: "empty", url: "" },
];
const excelImages = ref([]);
const docFiles = ref([]);
const folderInput = ref(null);
let imageSyncTimer = null;
const IMAGE_SUFFIXES = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]);
const doc = reactive({
  categoryId: "",
  categoryName: "",
  batch: null,
  templateId: "",
  templateName: "",
  templateReason: "",
});
const docGrid = reactive({
  columns: [],
  rows: [],
  row_issues: [],
  warnings: [],
  row_count: 0,
  ready_count: 0,
  source: "",
  loading: false,
  checking: false,
  generating: false,
  regenerating: false,
  selectAll: false,
});
const docProgress = ref({ done: 0 });
let docTimer = null;
let gridPollTimer = null;
const excel = reactive({
  photoPolicy: "complete",
  emptyPolicy: "draw",
});
const smartPlan = ref({ columns: [], column_count: 0, reasoning: "", tips: "", category_name: "" });
const ecosystemBrief = ref(null);
const smartPlanLoading = ref(false);
const docTemplateDownloading = ref(false);
const categoryBrowser = ref(false);
const categoryTemplates = ref([]);
const templateLoading = ref(false);
const templateSuggesting = ref(false);
const aiServiceReady = ref(null);
const reviewAssistRunning = ref(false);
let reviewAssistPromise = null;
const reviewAiSteps = ref(createReviewAiSteps());
const smartPlanAiSteps = ref(createSmartPlanAiSteps());
let smartPlanStepTimer = null;
let smartPlanStepStartedAt = 0;

function createSmartPlanAiSteps() {
  return [
    { id: "schema", label: "读取官方字段", status: "pending", detail: "" },
    { id: "habits", label: "对照店铺模板", status: "pending", detail: "" },
    { id: "plan", label: "规划最短填写列", status: "pending", detail: "" },
  ];
}

function resetSmartPlanAiSteps() {
  smartPlanAiSteps.value = createSmartPlanAiSteps();
}

function patchSmartPlanStep(id, patch) {
  smartPlanAiSteps.value = smartPlanAiSteps.value.map((step) => (step.id === id ? { ...step, ...patch } : step));
}

function startSmartPlanStepAnimation() {
  clearSmartPlanStepAnimation();
  resetSmartPlanAiSteps();
  smartPlanStepStartedAt = Date.now();
  patchSmartPlanStep("schema", { status: "running", detail: "拉取类目 schema…" });
  smartPlanStepTimer = window.setInterval(() => {
    if (!smartPlanLoading.value) return;
    const elapsed = Date.now() - smartPlanStepStartedAt;
    if (elapsed >= 900) {
      patchSmartPlanStep("schema", { status: "done", detail: "" });
      patchSmartPlanStep("habits", { status: "running", detail: "店铺默认与刊登模板…" });
    }
    if (elapsed >= 1800) {
      patchSmartPlanStep("habits", { status: "done", detail: "" });
      patchSmartPlanStep("plan", { status: "running", detail: "LLM 规划填写列…" });
    }
  }, 400);
}

function clearSmartPlanStepAnimation() {
  if (smartPlanStepTimer) {
    clearInterval(smartPlanStepTimer);
    smartPlanStepTimer = null;
  }
  smartPlanStepStartedAt = 0;
}

function finishSmartPlanStepAnimation() {
  clearSmartPlanStepAnimation();
  smartPlanAiSteps.value = smartPlanAiSteps.value.map((step) => ({
    ...step,
    status: "done",
    detail: step.id === "plan" ? "完成" : "",
  }));
}

function createReviewAiSteps() {
  return [
    { id: "service", label: "检查 AI 服务", status: "pending", detail: "" },
    { id: "template", label: "匹配刊登模板", status: "pending", detail: "" },
    { id: "copy", label: "写标题和关键词", status: "pending", detail: "" },
    { id: "attrs", label: "推断官方属性", status: "pending", detail: "" },
    { id: "images", label: "配对/生成商品图", status: "pending", detail: "" },
    { id: "check", label: "更新校验结果", status: "pending", detail: "" },
  ];
}

function resetReviewAiSteps() {
  reviewAiSteps.value = createReviewAiSteps();
}

function patchReviewStep(id, patch) {
  reviewAiSteps.value = reviewAiSteps.value.map((step) => (step.id === id ? { ...step, ...patch } : step));
}

function reviewStepStatusLabel(status) {
  if (status === "running") return "进行中";
  if (status === "done") return "完成";
  if (status === "error") return "失败";
  if (status === "skip") return "跳过";
  return "等待";
}

const showReviewAiTimeline = computed(() => {
  if (docStep.value !== 0) return false;
  if (docGrid.loading || reviewAssistRunning.value) return true;
  return reviewAiSteps.value.some((step) => step.status !== "pending");
});

const reviewAiAllDone = computed(() => {
  if (docGrid.loading || reviewAssistRunning.value || hasPendingImageJobs()) return false;
  return reviewAiSteps.value.every((step) => ["done", "skip"].includes(step.status));
});

const coreFillIds = new Set(["sku", "price", "moq", "images", "brand", "name", "note"]);
const copyColumnIds = new Set(["title", "keywords", "highlights"]);
const tableCoreIds = new Set(["sku", "name", "price", "moq", "brand", "note", "title", "keywords", "highlights"]);
const smartColumnLabels = computed(() => (smartPlan.value.columns || []).map((col) => col.label).filter(Boolean));
const uploadSummary = computed(() => {
  const sheets = docFiles.value.filter((item) => isSpreadsheetFile(item.name)).length;
  const images = docFiles.value.filter((item) => isImageFile(item.name)).length;
  if (!sheets && !images) return "";
  const bits = [];
  if (sheets) bits.push(`${sheets} 个表格`);
  if (images) bits.push(`${images} 张图片`);
  return `已选 ${bits.join("，")}`;
});
const excelImageMode = computed(() => `${excel.photoPolicy || "complete"}_${excel.emptyPolicy || "draw"}`);
const docPercent = computed(() => {
  if (!doc.batch?.count) return 0;
  return Math.min(100, Math.round((docProgress.value.done / doc.batch.count) * 100));
});
const docDataColumns = computed(() => docGrid.columns.filter((col) => col.id !== "images"));
const auditTableColSpan = computed(() => 5 + docDataColumns.value.length);
const docRequiredAttrColumns = computed(() =>
  docDataColumns.value.filter((col) => col.required && !copyColumnIds.has(col.id) && !tableCoreIds.has(col.id)),
);
const docScoreAttrColumns = computed(() =>
  docDataColumns.value.filter(
    (col) =>
      !col.required
      && (col.source === "schema_score" || col.id.startsWith("attr.") || col.id.startsWith("schema.")),
  ),
);
const docSelectedCount = computed(() => docGrid.rows.filter((row) => row._selected).length);
const templateRowOverrideCount = computed(() => {
  if (!doc.templateId) {
    return docGrid.rows.filter((row) => row._template_id).length;
  }
  return docGrid.rows.filter((row) => row._template_id && row._template_id !== doc.templateId).length;
});
const hasBrandColumn = computed(() => docGrid.columns.some((col) => col.id === "brand"));
const issueLineSet = computed(() => new Set((docGrid.row_issues || []).map((item) => item.line)));
const reviewStats = computed(() => {
  const rows = docGrid.rows || [];
  const issues = issueLineSet.value;
  let ready = 0;
  let imagesOk = 0;
  let copyOk = 0;
  let issueCount = 0;
  rows.forEach((row) => {
    if (rowReady(row)) ready += 1;
    if (rowImageCount(row) >= 6) imagesOk += 1;
    if (!rowMissingCopy(row)) copyOk += 1;
    if (issues.has(row.line)) issueCount += 1;
  });
  return {
    total: rows.length,
    ready,
    imagesOk,
    copyOk,
    issueCount,
    selected: docSelectedCount.value,
  };
});
const auditStats = computed(() => {
  const rows = docGrid.rows || [];
  let pending = 0;
  let approved = 0;
  let rejected = 0;
  rows.forEach((row) => {
    const status = rowAuditStatus(row);
    if (status === "approved") approved += 1;
    else if (status === "rejected") rejected += 1;
    else pending += 1;
  });
  return { pending, approved, rejected, total: rows.length };
});
const auditFilterOptions = computed(() => [
  { id: "all", label: "全部", count: auditStats.value.total },
  { id: "pending", label: "待审核", count: auditStats.value.pending },
  { id: "approved", label: "审核通过", count: auditStats.value.approved },
  { id: "rejected", label: "审核不通过", count: auditStats.value.rejected },
]);
const rowDetailTitle = computed(() => {
  if (!rowDetailRow.value) return "商品详情";
  return rowDetailRow.value.name || rowDetailRow.value.sku || "商品详情";
});
const filteredDocRowViews = computed(() => {
  const q = reviewSearch.value.trim().toLowerCase();
  return docGrid.rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => {
      switch (reviewFilter.value) {
        case "pending":
          return rowAuditStatus(row) === "pending";
        case "approved":
          return rowAuditStatus(row) === "approved";
        case "rejected":
          return rowAuditStatus(row) === "rejected";
        case "issues":
          return rowHasIssues(row);
        case "no_images":
          return rowImageCount(row) < 6;
        case "no_copy":
          return rowMissingCopy(row);
        case "not_ready":
          return !rowReady(row);
        case "selected":
          return row._selected;
        default:
          return true;
      }
    })
    .filter(({ row }) => {
      if (!q) return true;
      const haystack = docDataColumns.value
        .map((col) => row[col.id])
        .concat([row.sku, row.name, row.title, row.keywords])
        .map((value) => String(value || "").toLowerCase())
        .join(" ");
      return haystack.includes(q);
    });
});
const paginatedDocRowViews = computed(() => {
  const start = (reviewPage.value - 1) * reviewPageSize.value;
  return filteredDocRowViews.value.slice(start, start + reviewPageSize.value);
});
const otherSessions = computed(() => openSessions.value.filter((item) => item.id !== sessionId.value));
const docImageGenSummary = computed(() => {
  const rows = docGrid.rows || [];
  if (!rows.length) return "";
  let running = 0;
  let ready = 0;
  rows.forEach((row) => {
    const status = String(row.image_job_status || "");
    if (["queued", "running"].includes(status)) running += 1;
    if (rowSlots(row).filter((slot) => slot.url).length >= 6) ready += 1;
  });
  if (running) return `出图中 ${running}/${rows.length} 行`;
  if (ready === rows.length) return `图片已齐 ${ready}/${rows.length} 行`;
  return `待出图 ${rows.length - ready} 行`;
});

function applyExcelImageMode(raw, photo, empty) {
  if (photo && empty) {
    excel.photoPolicy = photo;
    excel.emptyPolicy = empty;
    return;
  }
  const aliases = {
    mixed: "keep_draw",
    photos_only: "keep_skip",
    generate_all: "boost_draw",
    keep: "keep_draw",
    complete: "complete_draw",
    boost: "boost_draw",
  };
  const mode = aliases[raw] || raw || "complete_draw";
  const [nextPhoto, nextEmpty] = String(mode).split("_");
  excel.photoPolicy = ["keep", "complete", "boost"].includes(nextPhoto) ? nextPhoto : "complete";
  excel.emptyPolicy = nextEmpty === "skip" ? "skip" : "draw";
}


function migrateLegacyExcelSession(session, payload) {
  if (session.path !== "excel" && session.path !== "full") return;
  const ep = payload.excel || {};
  if (!doc.categoryId && ep.categoryId) {
    doc.categoryId = ep.categoryId;
    doc.categoryName = ep.categoryName || payload.categoryName || "";
  }
  if (!doc.batch && ep.batch) doc.batch = ep.batch;
  applyExcelImageMode(ep.imageMode, ep.photoPolicy, ep.emptyPolicy);
  const stepMap = { 0: 0, 1: 0, 2: 1, 3: 1, 4: 1 };
  docStep.value = stepMap[session.step ?? 0] ?? 0;
  docReached.value = Math.max(session.reached ?? 0, docStep.value);
}

function sessionPayload() {
  return {
    doc: {
      categoryId: doc.categoryId,
      categoryName: doc.categoryName,
      columns: docGrid.columns,
      rows: docGrid.rows,
      row_issues: docGrid.row_issues,
      warnings: docGrid.warnings,
      row_count: docGrid.row_count,
      ready_count: docGrid.ready_count,
      source: docGrid.source,
      batch: doc.batch,
      smartPlan: smartPlan.value,
      templateId: doc.templateId,
      templateName: doc.templateName,
      templateReason: doc.templateReason,
      imageMode: excelImageMode.value,
      photoPolicy: excel.photoPolicy,
      emptyPolicy: excel.emptyPolicy,
      uploadNames: docFiles.value.map((item) => item.name).filter(Boolean),
    },
    rowCount: docGrid.row_count || docGrid.rows.length || doc.batch?.count || 0,
    batchId: doc.batch?.batch_id || "",
  };
}

function currentStep() {
  return docStep.value;
}

function currentReached() {
  return docReached.value;
}

async function loadOpenSessions() {
  if (!store.user) return;
  try {
    const data = await api.feedSessions(store.shopId);
    openSessions.value = (data.sessions || []).filter(
      (item) => ["doc", "excel", "full"].includes(item.path) && !deadSessionIds.has(item.id),
    );
  } catch {
    openSessions.value = [];
  }
}

function bumpSessionGeneration() {
  sessionGeneration += 1;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isSessionApiMissing(error) {
  const status = Number(error?.status || 0);
  if (status === 404) return true;
  const msg = String(error?.message || "");
  return msg.includes("不在了") || /not found/i.test(msg);
}

async function saveSessionWithRetry(id, body) {
  let lastError = null;
  for (let attempt = 0; attempt < sessionApiRetryDelays.length + 1; attempt += 1) {
    try {
      return await api.saveFeedSession(id, body);
    } catch (error) {
      lastError = error;
      if (!isSessionApiMissing(error) || attempt >= sessionApiRetryDelays.length) throw error;
      await sleep(sessionApiRetryDelays[attempt]);
    }
  }
  throw lastError || new Error("保存失败");
}

async function uploadSessionFilesWithRetry(id, form) {
  let lastError = null;
  for (let attempt = 0; attempt < sessionApiRetryDelays.length + 1; attempt += 1) {
    try {
      return await api.uploadFeedSessionFiles(id, form);
    } catch (error) {
      lastError = error;
      if (!isSessionApiMissing(error) || attempt >= sessionApiRetryDelays.length) throw error;
      await sleep(sessionApiRetryDelays[attempt]);
    }
  }
  throw lastError || new Error("上传失败");
}

async function markSessionDeadAndRecover(deadId, options = {}) {
  const { quiet = true } = options;
  if (deadId) forgetSession(deadId);
  if (sessionId.value === deadId) {
    sessionId.value = "";
  }
  if (route.query.session === deadId) router.replace({ query: {} });
  clearTimeout(saveTimer);
  clearTimeout(imageSyncTimer);
  persistBlockedUntil = Date.now() + 1500;
  await migrateOrphanSession({ quiet });
  if (!quiet) ElMessage.warning("这条做到一半的记录已失效，已为你新建批量任务");
}

function verifySession(id) {
  if (!id || deadSessionIds.has(id)) return;
  verifiedSessionIds.value = new Set([...verifiedSessionIds.value, id]);
}

function loadDeadSessionIds() {
  const dead = new Set();
  try {
    const raw = sessionStorage.getItem(DEAD_SESSIONS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    if (Array.isArray(parsed)) {
      parsed.forEach((id) => {
        if (id) dead.add(String(id));
      });
    }
  } catch {
    /* ignore corrupt cache */
  }
  return dead;
}

function rememberOpenSession(id) {
  verifySession(id);
}

function forgetSession(id) {
  if (!id) return;
  deadSessionIds.add(id);
  bumpSessionGeneration();
  try {
    sessionStorage.setItem(DEAD_SESSIONS_KEY, JSON.stringify([...deadSessionIds].slice(-80)));
  } catch {
    /* sessionStorage may be unavailable */
  }
  const next = new Set(verifiedSessionIds.value);
  next.delete(id);
  verifiedSessionIds.value = next;
  openSessions.value = openSessions.value.filter((item) => item.id !== id);
}

function isKnownOpenSession(id) {
  return Boolean(id && !deadSessionIds.has(id) && verifiedSessionIds.value.has(id));
}

function sessionFromOpenList(id) {
  return openSessions.value.find((item) => item.id === id) || null;
}

async function migrateOrphanSession(options = {}) {
  const { quiet = true } = options;
  const payload = sessionPayload();
  const step = currentStep();
  const reached = currentReached();
  const staleId = sessionId.value;
  if (staleId) forgetSession(staleId);
  sessionId.value = "";
  if (route.query.session) router.replace({ query: {} });
  await startPath();
  if (!sessionId.value) return false;
  const generation = sessionGeneration;
  try {
    const saved = await saveSessionWithRetry(sessionId.value, {
      shop_id: store.shopId || "",
      step,
      reached,
      payload,
    });
    if (generation !== sessionGeneration) return false;
    verifySession(sessionId.value);
    currentTitle.value = saved.title || currentTitle.value;
    router.replace({ query: { session: sessionId.value } });
    return true;
  } catch {
    if (!quiet) ElMessage.error("无法恢复批量任务，请点「新建任务」重试");
    return false;
  }
}

async function ensureFeedSession(options = {}) {
  if (sessionEnsurePromise) return sessionEnsurePromise;
  sessionEnsurePromise = ensureFeedSessionImpl(options).finally(() => {
    sessionEnsurePromise = null;
  });
  return sessionEnsurePromise;
}

async function ensureFeedSessionImpl(options = {}) {
  const { quiet = false } = options;
  if (!sessionId.value) {
    await startPath();
    return Boolean(sessionId.value);
  }
  if (deadSessionIds.has(sessionId.value)) {
    sessionId.value = "";
    if (route.query.session) router.replace({ query: {} });
    await startPath();
    return Boolean(sessionId.value);
  }
  if (isKnownOpenSession(sessionId.value)) {
    return true;
  }
  await loadOpenSessions();
  if (isKnownOpenSession(sessionId.value)) {
    return true;
  }
  if (sessionFromOpenList(sessionId.value)) {
    verifySession(sessionId.value);
    return true;
  }
  const staleId = sessionId.value;
  await markSessionDeadAndRecover(staleId, { quiet });
  return Boolean(sessionId.value);
}

async function persistSession() {
  if (persistInFlight) return persistInFlight;
  persistInFlight = persistSessionImpl().finally(() => {
    persistInFlight = null;
  });
  return persistInFlight;
}

async function persistSessionImpl() {
  if (sessionBooting.value || restoring.value || docGrid.loading || reviewAssistRunning.value) return;
  if (Date.now() < persistBlockedUntil) return;
  if (!sessionId.value || deadSessionIds.has(sessionId.value)) return;
  const generation = sessionGeneration;
  const targetId = sessionId.value;
  const ok = await ensureFeedSession({ quiet: true });
  if (generation !== sessionGeneration || sessionId.value !== targetId) return;
  if (!ok || !sessionId.value || deadSessionIds.has(sessionId.value)) return;
  if (!isKnownOpenSession(sessionId.value)) {
    await loadOpenSessions();
  }
  if (generation !== sessionGeneration || sessionId.value !== targetId) return;
  if (!isKnownOpenSession(sessionId.value)) {
    await migrateOrphanSession({ quiet: true });
    return;
  }
  try {
    const saved = await saveSessionWithRetry(sessionId.value, {
      shop_id: store.shopId || "",
      step: currentStep(),
      reached: currentReached(),
      payload: sessionPayload(),
    });
    if (generation !== sessionGeneration || sessionId.value !== targetId) return;
    rememberOpenSession(sessionId.value);
    currentTitle.value = saved.title || currentTitle.value;
  } catch (error) {
    if (!isSessionApiMissing(error)) return;
    await markSessionDeadAndRecover(targetId, { quiet: true });
  }
}



function applySession(session) {
  restoring.value = true;
  sessionId.value = session.id;
  rememberOpenSession(session.id);
  currentTitle.value = session.title || session.path_label;
  const payload = session.payload || {};
  if (payload.excel) {
    applyExcelImageMode(payload.excel.imageMode, payload.excel.photoPolicy, payload.excel.emptyPolicy);
  }
  if (payload.doc) {
    doc.categoryId = payload.doc.categoryId || "";
    doc.categoryName = payload.doc.categoryName || payload.categoryName || "";
    doc.batch = payload.doc.batch || null;
    doc.templateId = payload.doc.templateId || "";
    doc.templateName = payload.doc.templateName || "";
    doc.templateReason = payload.doc.templateReason || "";
    docGrid.columns = payload.doc.columns || [];
    docGrid.rows = normalizeDocRows(payload.doc.rows || []);
    docGrid.row_issues = payload.doc.row_issues || [];
    docGrid.warnings = payload.doc.warnings || [];
    docGrid.row_count = payload.doc.row_count || docGrid.rows.length;
    docGrid.ready_count = payload.doc.ready_count || 0;
    docGrid.source = payload.doc.source || "";
    if (payload.doc.smartPlan?.columns?.length) {
      smartPlan.value = normalizeSmartPlan(payload.doc.smartPlan);
    }
    applyExcelImageMode(payload.doc.imageMode, payload.doc.photoPolicy, payload.doc.emptyPolicy);
    const names = payload.doc.uploadNames || [];
    docFiles.value = names.map((name) => ({ name, status: "success" }));
  } else {
    doc.categoryId = "";
    doc.categoryName = "";
    doc.batch = null;
    doc.templateId = "";
    doc.templateName = "";
    doc.templateReason = "";
    docGrid.columns = [];
    docGrid.rows = [];
    docGrid.row_issues = [];
    docGrid.warnings = [];
    docGrid.row_count = 0;
    docGrid.ready_count = 0;
    docGrid.source = "";
    docFiles.value = [];
  }
  if (session.path === "excel" || session.path === "full") {
    migrateLegacyExcelSession(session, payload);
  } else {
    docStep.value = Math.min(session.step || 0, docSteps.length - 1);
    if (docStep.value > 1) docStep.value = 1;
    docReached.value = Math.min(session.reached ?? 0, docSteps.length - 1);
  }
  restoring.value = false;
  if (doc.categoryId && store.shopId) {
    void loadCategoryTemplates();
  }
}

async function startPath() {
  if (startPathPromise) return startPathPromise;
  startPathPromise = startPathImpl().finally(() => {
    startPathPromise = null;
  });
  return startPathPromise;
}

async function startPathImpl() {
  try {
    const created = await api.createFeedSession({ path: "doc", shop_id: store.shopId || "" });
    docStep.value = 0;
    docReached.value = 0;
    doc.categoryId = "";
    doc.categoryName = "";
    doc.batch = null;
    doc.templateId = "";
    doc.templateName = "";
    doc.templateReason = "";
    docGrid.columns = [];
    docGrid.rows = [];
    docGrid.row_issues = [];
    docGrid.warnings = [];
    docGrid.row_count = 0;
    docGrid.ready_count = 0;
    docGrid.source = "";
    docFiles.value = [];
    smartPlan.value = { columns: [], column_count: 0, reasoning: "", tips: "", category_name: "" };
    applySession(created);
    verifySession(created.id);
    router.replace({ query: { session: created.id } });
    void loadOpenSessions();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function finishResumeSession() {
  if (doc.batch?.batch_id) {
    clearInterval(docTimer);
    docTimer = setInterval(pollDoc, 3000);
    void pollDoc();
  }
  if (!doc.categoryId || !store.shopId) return;
  try {
    await loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName });
    void loadEcosystemBrief({ categoryId: doc.categoryId, categoryName: doc.categoryName });
    ensureGridPolling();
    if (docStep.value === 1 && (rowsNeedingCopy().length || rowsNeedingImageJobs().length)) {
      void runReviewAssist(true);
    }
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function resumeSession(id, options = {}) {
  const { deferHeavy = true, skipListReload = false } = options;
  if (!id || deadSessionIds.has(id)) {
    await startPath();
    return;
  }
  if (!skipListReload) {
    await loadOpenSessions();
  }
  const session = sessionFromOpenList(id);
  if (!session) {
    forgetSession(id);
    if (route.query.session === id) router.replace({ query: {} });
    const fallback = openSessions.value.find((item) => !deadSessionIds.has(item.id));
    if (fallback && fallback.id !== id) {
      await resumeSession(fallback.id, options);
    } else {
      await startPath();
    }
    return;
  }
  applySession(session);
  verifySession(id);
  router.replace({ query: { session: id } });
  if (deferHeavy) {
    void finishResumeSession();
    return;
  }
  await finishResumeSession();
}

async function dropSession(id) {
  try {
    await api.dropFeedSession(id);
  } catch (error) {
    if (!isSessionApiMissing(error)) {
      ElMessage.error(error.message);
      return;
    }
  }
  forgetSession(id);
  if (sessionId.value === id) {
    sessionId.value = "";
    router.replace({ query: {} });
  }
  await loadOpenSessions();
}

async function dropCurrent() {
  if (sessionId.value) await dropSession(sessionId.value);
}

async function backToChooser() {
  await persistSession();
  await startPath();
}

async function bootSession() {
  sessionBooting.value = true;
  try {
    await loadOpenSessions();
    const wanted = route.query.session ? String(route.query.session) : "";
    if (wanted && deadSessionIds.has(wanted)) {
      router.replace({ query: {} });
    } else if (wanted && !deadSessionIds.has(wanted)) {
      const cached = sessionFromOpenList(wanted);
      if (cached) {
        applySession(cached);
        verifySession(wanted);
        router.replace({ query: { session: wanted } });
        void finishResumeSession();
        return;
      }
      forgetSession(wanted);
      router.replace({ query: {} });
    }
    const latest = openSessions.value.find((item) => !deadSessionIds.has(item.id));
    if (latest) {
      applySession(latest);
      verifySession(latest.id);
      router.replace({ query: { session: latest.id } });
      void finishResumeSession();
      return;
    }
    await startPath();
  } finally {
    sessionBooting.value = false;
  }
}

onMounted(async () => {
  const [, healthResult] = await Promise.allSettled([
    store.ensureShops().then(() => {
      if (store.shopId) void prefetchCategoryPicker(store.shopId);
    }),
    api.health(),
  ]);
  if (healthResult.status === "fulfilled") {
    aiServiceReady.value = healthResult.value.ai_enabled !== false;
  } else {
    aiServiceReady.value = null;
  }
  await bootSession();
});

let saveTimer = null;
watch(
  () => [excel.photoPolicy, excel.emptyPolicy],
  () => {
    if (sessionBooting.value || restoring.value || !sessionId.value || deadSessionIds.has(sessionId.value)) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persistSession, 400);
  },
);
watch(
  () => store.shopId,
  (shopId) => {
    if (shopId) void prefetchCategoryPicker(shopId);
  },
);
watch(
  () => docStep.value,
  (step) => {
    if (step === 1 && doc.categoryId && store.shopId) {
      void loadEcosystemBrief({ categoryId: doc.categoryId, categoryName: doc.categoryName });
    }
  },
);
watch(
  () => [docStep.value, doc.categoryId, doc.categoryName, docGrid.row_count, docGrid.ready_count, doc.templateId],
  () => {
    if (sessionBooting.value || restoring.value || docGrid.loading || reviewAssistRunning.value) return;
    if (!sessionId.value || deadSessionIds.has(sessionId.value)) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persistSession, 1500);
  },
);




function fileSuffix(name) {
  const lower = String(name || "").toLowerCase();
  const dot = lower.lastIndexOf(".");
  return dot >= 0 ? lower.slice(dot) : "";
}

function isImageFile(name) {
  return IMAGE_SUFFIXES.has(fileSuffix(name));
}

function isSpreadsheetFile(name) {
  return [".xlsx", ".xls", ".xlsm", ".csv"].includes(fileSuffix(name));
}

function slotsFromLocalUrls(urls) {
  const slots = DEFAULT_IMAGE_SLOTS.map((slot) => ({ ...slot }));
  (urls || []).slice(0, 6).forEach((url, index) => {
    if (!String(url || "").trim()) return;
    slots[index] = { ...slots[index], status: "uploaded", url: String(url).trim() };
  });
  return slots;
}

function applyLocalImageMatches(rows, files) {
  const uploads = buildUploadMap(files);
  if (!Object.keys(uploads).length) return rows;
  return rows.map((row) => {
    const names = String(row.images || "")
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean);
    const matched = matchUploadFiles(row.sku, names, uploads);
    if (!matched.length) return row;
    const mergedNames = [...new Set([...names, ...matched.map(([name]) => name)])];
    const urls = matched.map(([, raw]) => URL.createObjectURL(raw));
    return {
      ...row,
      images: mergedNames.join(";"),
      image_slots: slotsFromLocalUrls(urls),
    };
  });
}

function allUploadImageFiles() {
  const seen = new Set();
  const items = [];
  [...docFiles.value, ...excelImages.value].forEach((item) => {
    if (!item?.raw || !isImageFile(item.name)) return;
    const key = fileStorageKey(item.raw);
    if (seen.has(key)) return;
    seen.add(key);
    items.push(item);
  });
  return items;
}

function addDocFiles(files) {
  const existing = new Set(docFiles.value.map((item) => fileStorageKey(item.raw || { name: item.name })));
  let added = 0;
  files.forEach((file) => {
    if (!file) return;
    const key = fileStorageKey(file);
    if (!key || existing.has(key)) return;
    const label = file.webkitRelativePath || file.name;
    docFiles.value.push({ name: label, raw: file, status: "success" });
    existing.add(key);
    added += 1;
  });
  if (added) {
    docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
    scheduleDocImageSync();
  }
  return added;
}

function onDropFiles(event) {
  const files = Array.from(event.dataTransfer?.files || []);
  if (!files.length) return;
  const added = addDocFiles(files);
  if (added) {
    ElMessage.success(`已添加 ${added} 个文件`);
  } else {
    ElMessage.info("这些文件已经在列表里了");
  }
}

function pickImageFolder() {
  folderInput.value?.click();
}

function onFolderPick(event) {
  const picked = Array.from(event.target.files || []).filter((file) => isImageFile(file.name));
  if (!picked.length) {
    ElMessage.warning("文件夹里没找到图片");
    return;
  }
  const added = addDocFiles(picked);
  event.target.value = "";
  if (added) ElMessage.success(`已添加 ${added} 张图片`);
}

function onDocFilesChange() {
  scheduleDocImageSync();
}

function scheduleDocImageSync() {
  clearTimeout(imageSyncTimer);
  imageSyncTimer = setTimeout(() => {
    void syncDocImagesToSession();
  }, 800);
}

async function syncDocImagesToSession() {
  if (restoring.value || docGrid.loading || reviewAssistRunning.value) return;
  if (Date.now() < persistBlockedUntil) return;
  const ok = await ensureFeedSession({ quiet: true });
  if (!ok || !sessionId.value || !isKnownOpenSession(sessionId.value)) return;
  const images = allUploadImageFiles();
  if (!images.length) return;
  const targetId = sessionId.value;
  const form = new FormData();
  form.append("kind", "excel_images");
  images.forEach((item) => form.append("files", item.raw, item.name));
  try {
    await uploadSessionFilesWithRetry(targetId, form);
  } catch (error) {
    if (!isSessionApiMissing(error)) return;
    await markSessionDeadAndRecover(targetId, { quiet: true });
  }
}

async function loadEcosystemBrief(override = null) {
  const categoryId = override?.categoryId ?? doc.categoryId ?? "";
  const categoryName = override?.categoryName ?? doc.categoryName ?? smartPlan.value.category_name ?? "";
  if (!store.shopId || !categoryId) {
    ecosystemBrief.value = null;
    return;
  }
  try {
    ecosystemBrief.value = await api.excelEcosystemBrief({
      shop_id: store.shopId,
      category_id: categoryId,
      category_name: categoryName,
    });
  } catch {
    ecosystemBrief.value = null;
  }
}

async function loadSmartPlan(override = null) {
  const categoryId = override?.categoryId ?? doc.categoryId ?? "";
  const categoryName = override?.categoryName ?? doc.categoryName ?? "";
  if (!store.shopId || !categoryId) return;
  smartPlanLoading.value = true;
  startSmartPlanStepAnimation();
  try {
    smartPlan.value = normalizeSmartPlan(await api.excelSmartPlan({
      shop_id: store.shopId,
      category_id: categoryId,
      category_name: categoryName,
      ...(override?.refresh ? { refresh: true } : {}),
    }));
    docGrid.columns = smartPlan.value.columns || [];
    finishSmartPlanStepAnimation();
    void loadEcosystemBrief({ categoryId, categoryName });
  } catch (error) {
    const msg = String(error.message || "");
    if (msg.includes("店铺不存在")) {
      await store.ensureShops();
      if (store.shopId) {
        smartPlan.value = normalizeSmartPlan(await api.excelSmartPlan({
          shop_id: store.shopId,
          category_id: categoryId,
          category_name: categoryName,
          ...(override?.refresh ? { refresh: true } : {}),
        }));
        docGrid.columns = smartPlan.value.columns || [];
        finishSmartPlanStepAnimation();
        void loadEcosystemBrief({ categoryId, categoryName });
        return;
      }
    }
    clearSmartPlanStepAnimation();
    throw error;
  } finally {
    smartPlanLoading.value = false;
  }
}

function normalizeSmartPlan(raw) {
  const columns = (raw.columns || []).map((col) => ({
    id: col.id,
    header: col.header || col.label || col.id,
    label: col.label || col.header || col.id,
    required: Boolean(col.required),
    options: col.options,
    kind: col.kind,
    group: col.group,
    field_id: col.field_id,
    source: col.source,
  }));
  return {
    category_name: raw.category_name || "",
    column_count: raw.column_count || columns.length,
    columns,
    reasoning: raw.reasoning || "",
    tips: raw.tips || "",
    cached: Boolean(raw.cached),
    planner: raw.planner || "",
    covered_by_shop: raw.covered_by_shop || [],
    covered_by_template: raw.covered_by_template || [],
    ai_fills: raw.ai_fills || [],
  };
}

async function refreshSmartPlan() {
  if (!doc.categoryId) {
    ElMessage.warning("先选叶子类目");
    return;
  }
  try {
    await loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName, refresh: true });
    ElMessage.success(`已重新规划：需填 ${smartPlan.value.column_count || 0} 列`);
    await persistSession();
  } catch (error) {
    ElMessage.error(error.message);
  }
}




function openDocCategory() {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  categoryBrowser.value = true;
}

function advanceDoc(index) {
  docReached.value = Math.max(docReached.value, index);
  docStep.value = index;
  void persistSession();
  if (index === 1) void runReviewAssist(true);
}

function rowSlots(row) {
  if (row?.image_slots?.length) return row.image_slots;
  return DEFAULT_IMAGE_SLOTS.map((slot) => ({ ...slot }));
}

function normalizeDocRows(rows) {
  return (rows || []).map((row, index) => ({
    ...row,
    line: row.line || index + 2,
    _selected: Boolean(row._selected),
    _audit_status: row._audit_status || "pending",
    image_slots: row.image_slots?.length ? row.image_slots : DEFAULT_IMAGE_SLOTS.map((slot) => ({ ...slot })),
  }));
}

function hasPendingImageJobs() {
  return docGrid.rows.some((row) => ["queued", "running"].includes(String(row.image_job_status || "")));
}

function ensureGridPolling() {
  if (gridPollTimer) return;
  if (!hasPendingImageJobs()) return;
  gridPollTimer = setInterval(pollGridImages, 2000);
  pollGridImages();
}

async function pollGridImages() {
  if (!docGrid.rows.length) return;
  try {
    const body = new FormData();
    body.append("rows", JSON.stringify(docGrid.rows));
    const result = await api.excelGridPollImages(body);
    docGrid.rows = normalizeDocRows(result.rows || []);
    if (!result.pending) {
      clearInterval(gridPollTimer);
      gridPollTimer = null;
      patchReviewStep("images", {
        status: "done",
        detail: `六图 ${reviewStats.value.imagesOk}/${reviewStats.value.total}`,
      });
      await recheckDocGrid({ silent: true });
    } else {
      patchReviewStep("images", {
        status: "running",
        detail: docImageGenSummary.value || "后台生成中…",
      });
    }
    await persistSession();
  } catch {
    clearInterval(gridPollTimer);
    gridPollTimer = null;
  }
}

function auditColumnClass(col) {
  if (col?.required) return "is-required-col";
  if (col?.source === "schema_score" || String(col?.id || "").startsWith("attr.") || String(col?.id || "").startsWith("schema.")) {
    return "is-score-col";
  }
  return "";
}

function rowHasIssues(row) {
  return issueLineSet.value.has(row.line);
}

function rowReady(row) {
  return Boolean(String(row.price || "").trim() && String(row.moq || "").trim());
}

function rowImageCount(row) {
  return rowSlots(row).filter((slot) => slot.url).length;
}

function rowMissingCopy(row) {
  return !String(row.title || "").trim() || !String(row.keywords || "").trim();
}

function rowAuditStatus(row) {
  return row._audit_status || "pending";
}

function rowStatusLabel(row) {
  const status = rowAuditStatus(row);
  if (status === "approved") return "审核通过";
  if (status === "rejected") return "审核不通过";
  return "待审核";
}

function formatAuditPrice(value) {
  const raw = String(value || "").trim();
  if (!raw) return "—";
  const num = Number(raw.replace(/[^\d.]/g, ""));
  if (Number.isFinite(num) && num > 0) return num.toFixed(2);
  return raw;
}

function rowAuditReady(row) {
  return !rowHasIssues(row) && rowReady(row) && !rowMissingCopy(row) && rowImageCount(row) >= 6;
}

function rowEmptyRequiredAttrs(row) {
  return docRequiredAttrColumns.value.filter((col) => !String(row[col.id] || "").trim());
}

function rowEmptyScoreAttrs(row) {
  return docScoreAttrColumns.value.filter((col) => !String(row[col.id] || "").trim());
}

function rowProductThumb(row) {
  const slot = rowSlots(row).find((item) => item.url);
  return slot?.url || "";
}

function approveRow(row) {
  row._audit_status = "approved";
  persistSession();
}

function rejectRow(row) {
  row._audit_status = "rejected";
  persistSession();
}

function batchApprove() {
  const targets = docGrid.rows.filter((row) => row._selected);
  if (!targets.length) {
    ElMessage.warning("先勾选要通过的商品");
    return;
  }
  targets.forEach((row) => {
    row._audit_status = "approved";
  });
  persistSession();
  ElMessage.success(`已通过 ${targets.length} 个商品`);
}

function batchReject() {
  const targets = docGrid.rows.filter((row) => row._selected);
  if (!targets.length) {
    ElMessage.warning("先勾选要不通过的商品");
    return;
  }
  targets.forEach((row) => {
    row._audit_status = "rejected";
  });
  persistSession();
  ElMessage.success(`已标记 ${targets.length} 个商品为未通过`);
}

function openRowDetail(view) {
  rowDetailRow.value = view.row;
  rowDetailOpen.value = true;
}

function pickReviewImages() {
  reviewImageInput.value?.click();
}

function onReviewImagePick(event) {
  const picked = Array.from(event.target.files || []).filter((file) => isImageFile(file.name));
  event.target.value = "";
  if (!picked.length) {
    ElMessage.warning("请选择图片文件");
    return;
  }
  const added = addDocFiles(picked);
  docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
  if (added) {
    ElMessage.success(`已配对 ${added} 张图片`);
    void recheckDocGrid({ silent: true });
    persistSession();
  }
}

function onReviewImageDrop(event) {
  const files = Array.from(event.dataTransfer?.files || []).filter((file) => isImageFile(file.name));
  if (!files.length) return;
  const added = addDocFiles(files);
  docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
  if (added) {
    ElMessage.success(`已配对 ${added} 张图片`);
    void recheckDocGrid({ silent: true });
    persistSession();
  }
}

async function inferFieldsForRows(lines, options = {}) {
  const { silent = false } = options;
  if (!docGrid.rows.length) return { ok: true, skipped: true };
  docInferring.value = true;
  try {
    const body = new FormData();
    body.append("shop_id", store.shopId || "");
    body.append("category_id", doc.categoryId);
    if (docGrid.columns?.length) {
      body.append("columns", JSON.stringify(docGrid.columns));
    } else if (smartPlan.value.columns?.length) {
      body.append("columns", JSON.stringify(smartPlan.value.columns));
    }
    body.append("rows", JSON.stringify(docGrid.rows));
    body.append("lines", JSON.stringify(lines || []));
    const result = await api.excelGridInferFields(body);
    docGrid.rows = normalizeDocRows(result.rows || []);
    await recheckDocGrid({ silent: true });
    await persistSession();
    if (!silent) {
      if (result.filled_count) {
        ElMessage.success(`已从备注推断 ${result.filled_count} 个属性`);
      } else {
        ElMessage.info("没有找到有依据可补的空属性");
      }
    }
    return { ok: true, filled_count: result.filled_count || 0 };
  } catch (error) {
    if (!silent) ElMessage.error(error.message);
    return { ok: false, error: error.message };
  } finally {
    docInferring.value = false;
  }
}

function inferFieldsForSelection() {
  const lines = docGrid.rows.filter((row) => row._selected).map((row) => row.line);
  if (!lines.length) {
    ElMessage.warning("先勾选要推断属性的商品");
    return;
  }
  inferFieldsForRows(lines);
}

function inferFieldsForAll() {
  inferFieldsForRows([]);
}

function inferFieldsForRow(row) {
  inferFieldsForRows([row.line]);
}

function invertDocSelection() {
  docGrid.rows.forEach((row) => {
    row._selected = !row._selected;
  });
  docGrid.selectAll = docGrid.rows.length > 0 && docGrid.rows.every((row) => row._selected);
}

function clearDocSelection() {
  docGrid.selectAll = false;
  docGrid.rows.forEach((row) => {
    row._selected = false;
  });
}

function clearCopyFields(rows) {
  rows.forEach((row) => {
    row.title = "";
    row.keywords = "";
    row.highlights = "";
    delete row._copy_source;
  });
}

function clearCopyForSelection() {
  const targets = docGrid.rows.filter((row) => row._selected);
  if (!targets.length) {
    ElMessage.warning("先勾选要清空文案的行");
    return;
  }
  clearCopyFields(targets);
  persistSession();
}

function clearCopyForAll() {
  if (!docGrid.rows.length) return;
  clearCopyFields(docGrid.rows);
  persistSession();
}

function cloneDocRow(row, index) {
  const copy = JSON.parse(JSON.stringify(row));
  copy.line = docGrid.rows.length + 2 + index;
  copy._selected = false;
  copy.image_job_id = "";
  copy.image_job_status = "";
  copy.image_slots = DEFAULT_IMAGE_SLOTS.map((slot) => ({ ...slot }));
  if (copy.sku) copy.sku = `${copy.sku}-copy`;
  return copy;
}

function duplicateSelectedRows() {
  const selected = docGrid.rows.filter((row) => row._selected);
  if (!selected.length) {
    ElMessage.warning("先勾选要复制的行");
    return;
  }
  selected.forEach((row, index) => {
    docGrid.rows.push(cloneDocRow(row, index));
  });
  docGrid.row_count = docGrid.rows.length;
  persistSession();
  ElMessage.success(`已复制 ${selected.length} 行`);
}

function duplicateDocRow(index) {
  docGrid.rows.splice(index + 1, 0, cloneDocRow(docGrid.rows[index], 0));
  docGrid.row_count = docGrid.rows.length;
  persistSession();
}

async function deleteSelectedRows() {
  const count = docSelectedCount.value;
  if (!count) {
    ElMessage.warning("先勾选要删除的行");
    return;
  }
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${count} 行吗？`, "删除行", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    docGrid.rows = docGrid.rows.filter((row) => !row._selected);
    docGrid.row_count = docGrid.rows.length;
    docGrid.selectAll = false;
    await recheckDocGrid();
  } catch {
    /* cancelled */
  }
}

async function refreshGridImages() {
  if (!docGrid.rows.length) return;
  docGrid.generating = true;
  try {
    await pollGridImages();
    ElMessage.success("已刷新出图状态");
  } finally {
    docGrid.generating = false;
  }
}

function toggleSelectAll(checked) {
  docGrid.rows.forEach((row) => {
    row._selected = Boolean(checked);
  });
}

async function batchSetField(field) {
  const labels = { price: "单价 USD", moq: "起订量", brand: "品牌" };
  const label = labels[field] || field;
  const targets = docGrid.rows.filter((row) => row._selected);
  if (!targets.length) {
    ElMessage.warning("先勾选要改的行");
    return;
  }
  try {
    const { value } = await ElMessageBox.prompt(`批量填写${label}`, "批量修改", {
      confirmButtonText: "应用到选中行",
      cancelButtonText: "取消",
    });
    if (!String(value || "").trim()) return;
    targets.forEach((row) => {
      row[field] = String(value).trim();
    });
    await recheckDocGrid();
  } catch {
    /* cancelled */
  }
}

async function generateImagesForRows(lines, options = {}) {
  const { silent = false } = options;
  if (!docGrid.rows.length) return { ok: true, skipped: true };
  docGrid.generating = true;
  try {
    const body = new FormData();
    body.append("shop_id", store.shopId || "");
    body.append("category_id", doc.categoryId);
    body.append("category_name", doc.categoryName || smartPlan.value.category_name || "");
    body.append("rows", JSON.stringify(docGrid.rows));
    body.append("lines", JSON.stringify(lines || []));
    const result = await api.excelGridGenerateImages(body);
    docGrid.rows = normalizeDocRows(result.rows || []);
    if (result.errors?.length) {
      if (!silent) ElMessage.warning(result.errors[0]);
      return { ok: false, error: result.errors[0] };
    }
    ensureGridPolling();
    await persistSession();
    if (!silent) {
      ElMessage.success(lines?.length ? "已开始为选中行出图" : "已开始为全部商品出图");
    }
    return { ok: true };
  } catch (error) {
    if (!silent) ElMessage.error(error.message);
    return { ok: false, error: error.message };
  } finally {
    docGrid.generating = false;
  }
}

function rowsNeedingImageJobs() {
  return docGrid.rows.filter((row) => {
    const filled = rowSlots(row).filter((slot) => slot.url).length;
    if (filled >= 6) return false;
    const status = String(row.image_job_status || "");
    if (row.image_job_id && ["queued", "running"].includes(status)) return false;
    return true;
  });
}

async function autoStartReviewImages() {
  if (docStep.value !== 1 || !docGrid.rows.length || !doc.categoryId) return;
  if (!rowsNeedingImageJobs().length) {
    ensureGridPolling();
    return;
  }
  await generateImagesForRows([], { silent: true });
}

function generateImagesForSelection() {
  const lines = docGrid.rows.filter((row) => row._selected).map((row) => row.line);
  if (!lines.length) {
    ElMessage.warning("先勾选要出图的行");
    return;
  }
  generateImagesForRows(lines);
}

function generateImagesForAll() {
  generateImagesForRows([]);
}

function generateImagesForRow(row) {
  generateImagesForRows([row.line]);
}

async function regenCopyForRows(lines, options = {}) {
  const { silent = false } = options;
  if (!docGrid.rows.length) return { ok: true, skipped: true };
  docGrid.regenerating = true;
  try {
    const body = new FormData();
    body.append("shop_id", store.shopId || "");
    body.append("category_id", doc.categoryId);
    body.append("category_name", doc.categoryName || smartPlan.value.category_name || "");
    body.append("rows", JSON.stringify(docGrid.rows));
    body.append("lines", JSON.stringify(lines || []));
    const result = await api.excelGridRegenCopy(body);
    docGrid.rows = normalizeDocRows(result.rows || []);
    const copyOk = docGrid.rows.filter((row) => !rowMissingCopy(row)).length;
    if (result.errors?.length) {
      if (!silent) ElMessage.warning(result.errors[0]);
      return { ok: false, error: result.errors[0], copyOk };
    }
    await persistSession();
    if (!silent) {
      ElMessage.success(lines?.length ? "已重写选中行文案" : "已重写全部文案");
    }
    return { ok: true, copyOk };
  } catch (error) {
    if (!silent) ElMessage.error(error.message);
    return { ok: false, error: error.message };
  } finally {
    docGrid.regenerating = false;
  }
}

function rowsNeedingCopy() {
  return docGrid.rows.filter((row) => rowMissingCopy(row));
}

async function autoStartReviewCopy() {
  if (!docGrid.rows.length || !doc.categoryId) return { ok: true, skipped: true };
  if (!rowsNeedingCopy().length) return { ok: true, skipped: true, copyOk: docGrid.rows.length };
  const need = rowsNeedingCopy().length;
  patchReviewStep("copy", { status: "running", detail: `共 ${need} 行` });
  const result = await regenCopyForRows([], { silent: true });
  return result;
}

async function loadCategoryTemplates() {
  if (!store.shopId || !doc.categoryId) {
    categoryTemplates.value = [];
    return;
  }
  templateLoading.value = true;
  try {
    categoryTemplates.value = await api.templates({ shop_id: store.shopId, category_id: doc.categoryId });
  } catch {
    categoryTemplates.value = [];
  } finally {
    templateLoading.value = false;
  }
}

function applyTemplateToRows(templateId, templateName, reason, rowsFromApi) {
  const byLine = new Map((rowsFromApi || []).map((row) => [row.line, row]));
  docGrid.rows = docGrid.rows.map((row) => {
    const picked = byLine.get(row.line);
    if (picked) {
      return {
        ...row,
        _template_id: picked._template_id || templateId || "",
        _template_name: picked._template_name || templateName || "",
        _template_reason: picked._template_reason || reason || "",
      };
    }
    if (templateId) {
      return {
        ...row,
        _template_id: templateId,
        _template_name: templateName || "",
        _template_reason: reason || "",
      };
    }
    return row;
  });
}

async function suggestTemplates(force = false) {
  if (!docGrid.rows.length || !doc.categoryId || !store.shopId) {
    return { ok: true, skipped: true };
  }
  if (templateSuggesting.value && !force) {
    return { ok: true, skipped: true };
  }
  templateSuggesting.value = true;
  try {
    await loadCategoryTemplates();
    const body = new FormData();
    body.append("shop_id", store.shopId);
    body.append("category_id", doc.categoryId);
    body.append("category_name", doc.categoryName || smartPlan.value.category_name || "");
    body.append("rows", JSON.stringify(docGrid.rows));
    const result = await api.excelGridSuggestTemplate(body);
    if (result.templates?.length) {
      categoryTemplates.value = result.templates;
    }
    const suggestion = result.suggestion || {};
    doc.templateId = suggestion.template_id || "";
    doc.templateName = suggestion.template_name || "";
    doc.templateReason = suggestion.reasoning || "";
    applyTemplateToRows(doc.templateId, doc.templateName, doc.templateReason, result.rows);
    await persistSession();
    return { ok: true, suggestion };
  } catch (error) {
    return { ok: false, error: error.message };
  } finally {
    templateSuggesting.value = false;
  }
}

function onTemplateChange(templateId) {
  const picked = categoryTemplates.value.find((item) => item.id === templateId);
  doc.templateName = picked?.name || "";
  doc.templateReason = templateId ? "你手动选择了刊登模板" : "";
  applyTemplateToRows(templateId, doc.templateName, doc.templateReason);
  persistSession();
}

function onRowTemplateChange(row) {
  const picked = categoryTemplates.value.find((item) => item.id === row._template_id);
  row._template_name = picked?.name || "";
  row._template_reason = row._template_id ? "你手动改了这一行的模板" : "";
  persistSession();
}

async function runReviewAssist(force = false) {
  if (!docGrid.rows.length || !doc.categoryId) return;
  if (reviewAssistPromise) {
    if (!force) return reviewAssistPromise;
    try {
      await reviewAssistPromise;
    } catch {
      /* supersede failed run */
    }
  }
  reviewAssistPromise = runReviewAssistImpl(force).finally(() => {
    reviewAssistPromise = null;
  });
  return reviewAssistPromise;
}

async function runReviewAssistImpl(force = false) {
  if (!docGrid.rows.length || !doc.categoryId) return;
  reviewAssistRunning.value = true;
  resetReviewAiSteps();
  try {
    patchReviewStep("service", { status: "running", detail: "检查文案与出图服务…" });
    if (aiServiceReady.value === null) {
      try {
        const health = await api.health();
        aiServiceReady.value = health.ai_enabled !== false;
      } catch {
        aiServiceReady.value = null;
      }
    }

    patchReviewStep("template", { status: "running", detail: "匹配本店刊登习惯…" });
    const templateResult = await suggestTemplates(force);
    if (templateResult.skipped) {
      patchReviewStep("template", { status: "skip", detail: "暂无商品行" });
    } else if (templateResult.ok) {
      const name = doc.templateName || "未配置";
      patchReviewStep("template", {
        status: "done",
        detail: doc.templateId ? `已选「${name}」` : "本店无匹配模板，使用全局文案规则",
      });
    } else {
      patchReviewStep("template", { status: "error", detail: templateResult.error || "模板匹配失败" });
    }

    if (aiServiceReady.value === false) {
      patchReviewStep("service", { status: "error", detail: "未配置 OPENAI_API_KEY" });
      patchReviewStep("copy", { status: "skip", detail: "需要 AI 服务" });
      patchReviewStep("attrs", { status: "skip", detail: "需要 AI 服务" });
      patchReviewStep("images", { status: "skip", detail: "需要 AI 服务" });
    } else {
      patchReviewStep("service", { status: "done", detail: "服务可用" });

      const copyResult = await autoStartReviewCopy();
      if (copyResult.skipped) {
        patchReviewStep("copy", { status: "done", detail: "已有文案" });
      } else if (copyResult.ok) {
        patchReviewStep("copy", {
          status: "done",
          detail: `已完成 ${copyResult.copyOk || 0}/${docGrid.rows.length} 行`,
        });
      } else {
        patchReviewStep("copy", { status: "error", detail: copyResult.error || "文案生成失败" });
      }

      patchReviewStep("attrs", { status: "running", detail: "从备注推断官方属性…" });
      docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
      const inferResult = await inferFieldsForRows([], { silent: true });
      if (inferResult.skipped) {
        patchReviewStep("attrs", { status: "skip", detail: "无可推断字段" });
      } else if (inferResult.ok) {
        patchReviewStep("attrs", {
          status: "done",
          detail: inferResult.filled_count ? `补了 ${inferResult.filled_count} 个属性` : "属性已齐",
        });
      } else {
        patchReviewStep("attrs", { status: "error", detail: inferResult.error || "推断失败" });
      }

      const matchedPhotos = docGrid.rows.filter((row) => rowImageCount(row) > 0).length;
      const imageNeed = rowsNeedingImageJobs().length;
      if (imageNeed) {
        patchReviewStep("images", {
          status: "running",
          detail: matchedPhotos
            ? `已配对 ${matchedPhotos} 行，提交 ${imageNeed} 行补图…`
            : `提交 ${imageNeed} 行出图任务…`,
        });
        const imageResult = await generateImagesForRows([], { silent: true });
        if (imageResult.ok) {
          ensureGridPolling();
          patchReviewStep("images", {
            status: "running",
            detail: docImageGenSummary.value || "后台生成中…",
          });
        } else {
          patchReviewStep("images", { status: "error", detail: imageResult.error || "出图失败" });
        }
      } else if (matchedPhotos) {
        patchReviewStep("images", { status: "done", detail: `已配对 ${matchedPhotos}/${docGrid.rows.length} 行图片` });
      } else {
        patchReviewStep("images", { status: "done", detail: "图片已齐或任务进行中" });
      }
    }

    patchReviewStep("check", { status: "running", detail: "重新统计价量/文案/图片…" });
    await recheckDocGrid({ silent: true });
    patchReviewStep("check", {
      status: "done",
      detail: `文案 ${reviewStats.value.copyOk}/${reviewStats.value.total} · 六图 ${reviewStats.value.imagesOk}/${reviewStats.value.total}`,
    });
  } finally {
    reviewAssistRunning.value = false;
    void persistSession();
  }
}

function regenCopyForSelection() {
  const lines = docGrid.rows.filter((row) => row._selected).map((row) => row.line);
  if (!lines.length) {
    ElMessage.warning("先勾选要重写文案的行");
    return;
  }
  regenCopyForRows(lines);
}

function regenCopyForAll() {
  regenCopyForRows([]);
}

async function parseDocuments() {
  if (!doc.categoryId) {
    ElMessage.warning("先选叶子类目");
    return;
  }
  const uploadables = docFiles.value.filter((item) => item.raw);
  if (!uploadables.length) {
    ElMessage.warning("请先上传表格和图片（刷新页面后需重新选择文件）");
    return;
  }
  if (!uploadables.some((item) => isSpreadsheetFile(item.name))) {
    ElMessage.warning("至少上传一个 Excel/CSV 表格");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId || "");
  body.append("category_id", doc.categoryId);
  body.append("category_name", doc.categoryName || smartPlan.value.category_name || "");
  body.append("image_mode", excelImageMode.value);
  if (smartPlan.value.columns?.length) {
    body.append("columns", JSON.stringify(smartPlan.value.columns));
  }
  uploadables.forEach((item) => body.append("files", item.raw));
  docGrid.loading = true;
  parseStatus.value = "AI 正在读表…";
  resetReviewAiSteps();
  patchReviewStep("service", { status: "running", detail: "AI 正在读表…" });
  try {
    const result = await api.excelDocParse(body);
    docGrid.columns = result.columns || smartPlan.value.columns || [];
    if (result.download_columns?.length) {
      smartPlan.value = normalizeSmartPlan({ ...smartPlan.value, columns: result.download_columns, column_count: result.download_columns.length });
    }
    docGrid.rows = normalizeDocRows(applyLocalImageMatches(result.rows || [], uploadables));
    docGrid.row_issues = result.row_issues || [];
    docGrid.warnings = result.warnings || [];
    docGrid.row_count = result.row_count || docGrid.rows.length;
    docGrid.ready_count = result.ready_count || 0;
    docGrid.source = result.source || "";
    patchReviewStep("service", { status: "running", detail: "解析完成，AI 开始填写…" });
    void persistSession();
    await runReviewAssist(true);
    docReached.value = Math.max(docReached.value, 1);
    docStep.value = 1;
    ElMessage.success(`识别到 ${docGrid.row_count} 个商品，已进入审核`);
  } catch (error) {
    resetReviewAiSteps();
    ElMessage.error(error.message);
  } finally {
    docGrid.loading = false;
    parseStatus.value = "";
    void persistSession();
  }
}

async function recheckDocGrid(options = {}) {
  const { silent = false } = options;
  if (!docGrid.rows.length) return;
  const body = new FormData();
  body.append("shop_id", store.shopId || "");
  body.append("category_id", doc.categoryId);
  body.append("image_mode", excelImageMode.value);
  if (smartPlan.value.columns?.length) {
    body.append("columns", JSON.stringify(smartPlan.value.columns));
  }
  body.append("rows", JSON.stringify(docGrid.rows));
  docGrid.checking = true;
  try {
    const result = await api.excelGridCheck(body);
    docGrid.row_count = result.row_count || docGrid.rows.length;
    docGrid.ready_count = result.ready_count || 0;
    docGrid.row_issues = result.row_issues || [];
    await persistSession();
    if (!silent) {
      ElMessage.success(`校验完成：${docGrid.ready_count}/${docGrid.row_count} 个价量齐`);
    }
  } catch (error) {
    if (!silent) ElMessage.error(error.message);
  } finally {
    docGrid.checking = false;
  }
}

function addDocRow() {
  const row = { line: docGrid.rows.length + 2, _selected: false, image_slots: DEFAULT_IMAGE_SLOTS.map((slot) => ({ ...slot })) };
  (docGrid.columns.length ? docGrid.columns : smartPlan.value.columns || []).forEach((col) => {
    row[col.id] = "";
  });
  docGrid.rows.push(row);
  docGrid.row_count = docGrid.rows.length;
  persistSession();
}

function removeDocRow(index) {
  docGrid.rows.splice(index, 1);
  docGrid.row_count = docGrid.rows.length;
  persistSession();
}

async function importDocRows() {
  if (!docGrid.rows.length) {
    ElMessage.warning("表里还没有商品");
    return;
  }
  const approved = docGrid.rows.filter((row) => rowAuditStatus(row) === "approved");
  let targets = approved;
  if (!approved.length) {
    try {
      await ElMessageBox.confirm(
        "还没有标记「通过」的商品。要对当前全部商品成稿吗？建议先在表格里逐条审核并点 ✓。",
        "批量成稿",
        { confirmButtonText: "全部成稿", cancelButtonText: "先去审核", type: "warning" },
      );
      targets = docGrid.rows;
    } catch {
      return;
    }
  }
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("category_id", doc.categoryId);
  body.append("session_id", sessionId.value);
  body.append("image_mode", excelImageMode.value);
  if (smartPlan.value.columns?.length) {
    body.append("columns", JSON.stringify(smartPlan.value.columns));
  }
  if (doc.templateId) {
    body.append("listing_template_id", doc.templateId);
  }
  body.append("rows", JSON.stringify(targets));
  allUploadImageFiles().forEach((item) => body.append("images", item.raw, item.name));
  docGrid.loading = true;
  try {
    doc.batch = await api.excelImportRows(body);
    docProgress.value = { done: 0 };
    sessionId.value = "";
    clearInterval(docTimer);
    docTimer = setInterval(pollDoc, 3000);
    ElMessage.success(`已接收 ${doc.batch.count} 个商品，后台在成稿`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    docGrid.loading = false;
  }
}

async function pollDoc() {
  if (!doc.batch) return;
  try {
    docProgress.value = await api.batchProgress(doc.batch.batch_id, { total: doc.batch.count });
    if (docProgress.value.complete) clearInterval(docTimer);
  } catch {
    clearInterval(docTimer);
  }
}

function goDocBatchDrafts(filter = "pending") {
  router.push({ path: "/drafts", query: { batch_id: doc.batch.batch_id, filter } });
}

async function downloadDocTemplate() {
  if (!doc.categoryId) {
    ElMessage.warning("先选叶子类目");
    return;
  }
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  docTemplateDownloading.value = true;
  try {
    if (!smartPlan.value.columns?.length) {
      await loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName });
    }
    const categoryName = doc.categoryName || smartPlan.value.category_name || "";
    let blob;
    if (smartPlan.value.columns?.length) {
      blob = await api.excelSmartTemplateFromPlan({
        shop_id: store.shopId,
        category_id: doc.categoryId,
        category_name: categoryName,
        columns: smartPlan.value.columns,
        reasoning: smartPlan.value.reasoning,
        tips: smartPlan.value.tips,
        covered_by_shop: smartPlan.value.covered_by_shop,
        covered_by_template: smartPlan.value.covered_by_template,
        ai_fills: smartPlan.value.ai_fills,
      });
    } else {
      const response = await fetch(api.excelSmartTemplateUrl({
        categoryId: doc.categoryId,
        shopId: store.shopId,
        categoryName,
      }), { credentials: "include" });
      if (!response.ok) {
        let detail = "下载失败";
        try {
          const payload = await response.json();
          detail = payload.detail || detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }
      blob = await response.blob();
    }
    const safeName = (categoryName || doc.categoryId).replace(/[/\\?%*:|"<>]/g, "-");
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `智能批量上品-${safeName}.xlsx`;
    anchor.click();
    URL.revokeObjectURL(url);
    ElMessage.success("填写表已开始下载");
  } catch (error) {
    ElMessage.error(error.message || "下载失败");
  } finally {
    docTemplateDownloading.value = false;
  }
}


async function pickCategory(node) {
  await ensureFeedSession({ quiet: true });
  doc.categoryId = node.category_id;
  doc.categoryName = node.path_label || node.label || node.name || node.cn_name || "";
  try {
    await store.ensureShops();
    await loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName });
    ElMessage.success(`已选「${smartPlan.value.category_name || doc.categoryName}」`);
    await persistSession();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

onUnmounted(() => {
  clearInterval(docTimer);
  clearInterval(gridPollTimer);
  clearTimeout(imageSyncTimer);
  clearSmartPlanStepAnimation();
});








</script>

<style scoped>
.path-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 8px;
  margin-bottom: 18px;
}
.path-card-primary {
  border-color: var(--accent-line);
  background: var(--accent-wash);
}
.path-grid-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.path-grid-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
@media (min-width: 960px) {
  .path-grid-3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (min-width: 960px) {
  .path-grid-3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
.schema-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 16px 0 8px;
}
.schema-stat {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 999px;
  background: #f3f4f6;
  font-size: 13px;
}
.schema-stat.is-required {
  background: #fee2e2;
  color: #991b1b;
}
.schema-block summary {
  cursor: pointer;
  font-weight: 600;
}
.policy-block {
  margin-top: 16px;
}
.policy-block > small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 8px;
}
.policy-block .path-grid {
  margin-bottom: 0;
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
.chooser h3,
.resume-box h3 {
  margin: 0 0 6px;
  font-size: 16px;
}
.chooser {
  margin-bottom: 22px;
}
.resume-box {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px 16px;
  background: var(--surface);
}
.resume-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.resume-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.resume-card {
  flex: 1;
  text-align: left;
  border: 1px solid var(--line);
  background: var(--gray3);
  border-radius: var(--radius);
  padding: 10px 12px;
  cursor: pointer;
  font-family: inherit;
  color: inherit;
}
.resume-card b {
  display: block;
  margin-bottom: 2px;
}
.flow-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.boot-panel {
  padding: 24px 0;
}
.resume-inline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.resume-chip {
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 999px;
  padding: 4px 12px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  color: inherit;
}
.resume-chip:hover {
  border-color: var(--accent-line);
  background: var(--accent-wash);
}
.plan-panel {
  margin-top: 18px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 16px 18px;
  background: var(--surface);
}
.plan-panel-loading {
  background: var(--gray3);
}

.ai-timeline {
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: var(--surface);
  padding: 12px 16px 14px;
}

.ai-timeline-vertical {
  max-width: 420px;
}

.audit-ai-timeline {
  margin: 16px 0 14px;
  max-width: 480px;
}

.ecosystem-brief-panel {
  margin: 0 0 16px;
  padding: 14px 16px;
  border: 1px solid var(--line, #e8e8e8);
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(255, 153, 0, 0.06), transparent 72%);
  max-width: 640px;
}

.ecosystem-brief-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.ecosystem-brief-head strong {
  font-size: 15px;
}

.ecosystem-brief-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 153, 0, 0.15);
  color: #b45309;
}

.ecosystem-brief-tips {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text, #333);
}

.ecosystem-brief-steps {
  margin: 0 0 10px;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.65;
  color: var(--muted, #666);
}

.ecosystem-golden {
  margin-top: 8px;
}

.ecosystem-golden small {
  display: block;
  margin-bottom: 6px;
  color: var(--muted, #666);
  font-size: 12px;
}

.golden-title {
  margin: 0 0 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #334155;
}

.ecosystem-kw-tiers {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.kw-tier {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid var(--line, #e5e7eb);
  cursor: help;
}

.kw-tier.is-s {
  border-color: #16a34a;
  color: #166534;
  background: rgba(22, 163, 74, 0.08);
}

.kw-tier.is-a {
  border-color: #2563eb;
  color: #1d4ed8;
  background: rgba(37, 99, 235, 0.08);
}

.kw-tier.is-b {
  border-color: #ca8a04;
  color: #854d0e;
  background: rgba(202, 138, 4, 0.08);
}

.kw-tier.is-c {
  border-color: #dc2626;
  color: #991b1b;
  background: rgba(220, 38, 38, 0.06);
}

.ai-timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
}

.ai-timeline-head strong {
  font-weight: 600;
  color: var(--ink);
}

.ai-timeline-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
}

.ai-timeline-badge.is-live {
  color: var(--accent-text);
  background: var(--accent-wash);
}

.ai-timeline-badge.is-done {
  color: #166534;
  background: #dcfce7;
}

.ai-timeline-track {
  display: flex;
  flex-direction: column;
  gap: 0;
  list-style: none;
  margin: 0;
  padding: 0;
}

.ai-timeline-item {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  column-gap: 12px;
  align-items: stretch;
}

.ai-timeline-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 3px;
}

.ai-timeline-line {
  flex: 1;
  width: 2px;
  min-height: 18px;
  margin-top: 6px;
  border-radius: 999px;
  background: var(--line);
}

.ai-timeline-item.is-done .ai-timeline-line {
  background: color-mix(in srgb, var(--accent) 55%, var(--line));
}

.ai-timeline-item.is-running .ai-timeline-line {
  background: linear-gradient(to bottom, var(--accent) 0%, var(--line) 100%);
}

.ai-timeline-dot {
  flex: 0 0 auto;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--line);
  background: var(--surface);
  box-sizing: border-box;
}

.ai-timeline-item.is-running .ai-timeline-dot {
  width: 12px;
  height: 12px;
  border-color: var(--accent);
  background: var(--accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 16%, transparent);
}

.ai-timeline-item.is-done .ai-timeline-dot {
  border-color: var(--accent);
  background: var(--accent);
}

.ai-timeline-item.is-error .ai-timeline-dot {
  border-color: #dc2626;
  background: #dc2626;
}

.ai-timeline-item.is-skip .ai-timeline-dot {
  border-color: var(--muted);
  background: var(--gray3);
}

.ai-timeline-content {
  min-width: 0;
  padding-bottom: 14px;
}

.ai-timeline-item:last-child .ai-timeline-content {
  padding-bottom: 0;
}

.ai-timeline-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.ai-timeline-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.35;
}

.ai-timeline-item.is-pending .ai-timeline-label {
  color: var(--muted);
  font-weight: 500;
}

.ai-timeline-status {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--muted);
}

.ai-timeline-item.is-running .ai-timeline-status {
  color: var(--accent-text);
  font-weight: 600;
}

.ai-timeline-item.is-done .ai-timeline-status {
  color: #166534;
}

.ai-timeline-item.is-error .ai-timeline-status {
  color: #dc2626;
}

.ai-timeline-detail {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
  word-break: break-word;
}

.ai-timeline-item.is-running .ai-timeline-detail {
  color: var(--ink-2, var(--ink));
}

.ai-timeline-item.is-done .ai-timeline-detail {
  color: var(--muted);
}

.plan-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}
.plan-head h4 {
  margin: 0;
  font-size: 16px;
}
.plan-badge {
  display: inline-flex;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--accent-wash);
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}
.plan-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.plan-stat {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  background: var(--gray3);
}
.plan-stat strong {
  display: block;
  font-size: 22px;
  line-height: 1.1;
}
.plan-stat span {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}
.plan-stat-accent {
  border-color: var(--accent-line);
  background: var(--accent-wash);
}
.plan-coverage {
  margin: 0 0 10px;
  font-size: 12px;
}
.plan-reasoning {
  margin: 0 0 12px;
  line-height: 1.6;
}
.plan-columns small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 8px;
}
.plan-column-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.plan-tag {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--gray3);
  border: 1px solid var(--line);
  font-size: 12px;
}
.plan-tips {
  margin: 12px 0 0;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 13px;
}
.image-help {
  margin: 0 0 14px;
  padding: 12px 14px;
  border: 1px dashed var(--line);
  border-radius: var(--radius);
  background: var(--gray3);
  font-size: 13px;
}
.image-help h4 {
  margin: 0 0 8px;
  font-size: 14px;
}
.image-help p {
  margin: 0 0 8px;
  line-height: 1.5;
}
.image-help ol {
  margin: 0;
  padding-left: 18px;
  line-height: 1.6;
}
.image-help code {
  font-size: 12px;
  background: var(--surface);
  padding: 1px 4px;
  border-radius: 4px;
}
.plan-cache-note {
  margin: 8px 0 0;
  font-size: 12px;
}
.upload-flow-lead {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.6;
}
.upload-flow-simple code {
  font-size: 12px;
}
.upload-summary {
  margin: 8px 0 0;
  color: var(--accent);
  font-size: 13px;
}
.hidden-folder-input {
  display: none;
}
.upload-drop-zone {
  margin-top: 8px;
}
.upload-drop-inner {
  padding: 22px 12px;
}
.upload-drop-hint {
  margin: 8px 0 12px;
  font-size: 12px;
}
.upload-note {
  margin: 8px 0 0;
  font-size: 12px;
}
.upload-drop-zone :deep(.el-upload-dragger) {
  width: 100%;
  padding: 0;
  border-style: dashed;
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
  grid-template-columns: repeat(4, minmax(0, 1fr));
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
.sheet-preview-full table {
  min-width: max-content;
}
.sheet-preview th.is-required-col {
  background: #7f1d1d;
}
@media (max-width: 900px) {
  .path-grid,
  .path-grid-2,
  .policy-grid {
    grid-template-columns: 1fr;
  }
}

.photobank-panel {
  margin-top: 12px;
}

.photobank-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}

.photobank-item {
  border: 2px solid transparent;
  border-radius: 10px;
  padding: 6px;
  background: var(--panel);
  cursor: pointer;
  text-align: left;
}

.photobank-item.is-selected {
  border-color: var(--accent);
}

.photobank-item img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 8px;
  display: block;
}

.photobank-item span {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.category-next-box {
  margin-top: 16px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--gray3);
}

.category-next-box ul {
  margin: 10px 0 8px;
  padding-left: 18px;
  color: var(--ink-2);
}

.category-next-box li + li {
  margin-top: 6px;
}

.doc-grid-toolbar {
  display: flex;
  gap: 8px;
  margin: 12px 0;
}

.doc-grid-wrap {
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  max-height: 520px;
}

.doc-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.doc-grid th,
.doc-grid td {
  padding: 6px 8px;
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: middle;
}

.doc-grid th {
  background: var(--ink);
  color: #fff;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
}

.doc-grid .need {
  margin-left: 4px;
  font-size: 10px;
  font-weight: 500;
  color: #ffcdce;
}

.doc-grid td:first-child,
.doc-grid th:first-child {
  color: var(--muted);
  width: 36px;
  text-align: center;
}

.workspace-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.workspace-head-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.review-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.review-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) auto;
  gap: 16px 20px;
  align-items: end;
  padding: 18px 20px;
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: linear-gradient(180deg, var(--surface) 0%, var(--gray2) 100%);
}

.review-kicker {
  display: inline-block;
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent-text);
}

.review-hero-main h3 {
  margin: 0;
  font-size: 22px;
  line-height: 1.2;
}

.review-hero-meta {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 13px;
}

.review-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-self: center;
}

.review-metric {
  min-width: 72px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.review-metric strong {
  font-size: 15px;
  line-height: 1;
}

.review-metric span {
  font-size: 11px;
  color: var(--muted);
}

.review-metric.is-done {
  border-color: #b7ebc6;
  background: #f3fbf5;
}

.review-metric.is-done strong {
  color: #1a7f37;
}

.review-metric.is-warn {
  border-color: #f0d58a;
  background: #fffdf5;
}

.review-metric.is-warn strong {
  color: #9a6700;
}

.review-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-self: end;
}

.review-alert {
  margin: 12px 0 0;
}

.review-ai-progress {
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: var(--surface);
  padding: 14px 16px;
}

.review-ai-progress-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.review-ai-progress-head h4 {
  margin: 0;
  font-size: 14px;
}

.review-ai-steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}

.review-ai-steps li {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.review-ai-step-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  margin-top: 4px;
  background: var(--muted);
}

.review-ai-step-body {
  display: grid;
  gap: 2px;
}

.review-ai-step-body b {
  font-size: 13px;
}

.review-ai-step-body span {
  font-size: 12px;
  color: var(--muted);
}

.review-ai-step-body small {
  font-size: 12px;
  color: var(--text);
}

.review-ai-steps li.is-running .review-ai-step-dot {
  background: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-wash);
}

.review-ai-steps li.is-done .review-ai-step-dot {
  background: #16a34a;
}

.review-ai-steps li.is-error .review-ai-step-dot {
  background: #dc2626;
}

.review-ai-steps li.is-skip .review-ai-step-dot {
  background: #94a3b8;
}

.review-panel {
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: var(--surface);
  overflow: hidden;
}

.review-panel-top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
  background: var(--gray2);
}

.review-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.review-filter-pill {
  appearance: none;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
  color: var(--ink-2);
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.review-filter-pill small {
  margin-left: 6px;
  color: var(--muted);
  font-weight: 600;
}

.review-filter-pill:hover {
  border-color: var(--line-strong);
}

.review-filter-pill.is-active {
  border-color: var(--accent-line);
  background: var(--accent-wash);
  color: var(--accent-text);
}

.review-guide-toggle {
  border: none;
  background: transparent;
  color: var(--accent-text);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.review-guide {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
  background: var(--gray3);
}

.review-guide-item {
  padding: 10px 12px;
  border-radius: var(--radius);
  background: var(--surface);
  border: 1px solid var(--line);
}

.review-guide-item b {
  display: block;
  margin-bottom: 4px;
  font-size: 13px;
}

.review-guide-item span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

.review-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 16px;
  background: var(--surface);
}

.review-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: var(--line);
}

.review-tab-body {
  padding: 16px;
}

.review-tab-note {
  margin: 0 0 12px;
  color: var(--muted);
  font-size: 13px;
}

.review-tab-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.review-policy-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 12px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--line);
}

.review-policy-row label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
}

.review-grid-card {
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: var(--surface);
  overflow: hidden;
}

.review-grid-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line);
  background: var(--gray2);
}

.review-grid-scroll {
  max-height: min(62vh, 720px);
  overflow: auto;
}

.review-grid th {
  background: var(--gray12);
  color: #fff;
}

.review-empty {
  text-align: center;
  padding: 32px 12px;
  color: var(--muted);
}

.review-issues {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #fffdf5;
  padding: 0 14px 12px;
}

.review-issues summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 0;
  cursor: pointer;
  font-weight: 600;
  list-style: none;
}

.review-issues summary::-webkit-details-marker {
  display: none;
}

.review-issues ul {
  margin: 0;
  padding-left: 0;
  list-style: none;
}

.review-issues li {
  padding: 6px 0;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 13px;
}

.review-actionbar {
  position: sticky;
  bottom: 0;
  z-index: 2;
  margin-top: 4px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(10px);
}

.review-actionbar-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
}

.review-actionbar-main p {
  margin: 0;
  font-size: 13px;
}

.review-batch-progress {
  margin-top: 4px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface);
}

.col-status {
  min-width: 72px;
}

.col-row-actions {
  min-width: 148px;
  white-space: nowrap;
}

.row-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: var(--gray3);
  color: var(--muted);
}

.row-badge.is-ok {
  background: #dafbe1;
  color: #1a7f37;
}

.row-badge.is-warn {
  background: #fff8c5;
  color: #9a6700;
}

.review-grid tr.is-issue td {
  background: #fffdf5;
}

.review-grid tr.is-selected td {
  background: var(--accent-wash);
}

@media (max-width: 960px) {
  .review-hero {
    grid-template-columns: 1fr;
  }

  .review-guide {
    grid-template-columns: 1fr;
  }
}

.doc-grid-wide {
  min-width: max-content;
}

.col-check {
  width: 36px;
  text-align: center;
}

.col-slots {
  min-width: 420px;
}

.slot-strip {
  display: grid;
  grid-template-columns: repeat(6, 64px);
  gap: 6px;
}

.slot-thumb {
  aspect-ratio: 1;
  border-radius: 6px;
  border: 1px dashed var(--line);
  background: var(--gray3);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  font-size: 11px;
  color: var(--muted);
}

.slot-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.slot-thumb.is-queued,
.slot-thumb.is-running {
  border-color: var(--accent-line);
  background: var(--accent-wash);
  color: var(--accent);
}

.slot-thumb.is-done,
.slot-thumb.is-uploaded {
  border-style: solid;
}

.slot-thumb.is-empty {
  opacity: 0.85;
}

.upload-flow-steps {
  margin: 0;
  padding-left: 18px;
  line-height: 1.65;
  font-size: 13px;
}

.upload-flow-steps li + li {
  margin-top: 6px;
}

.audit-shell {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: calc(100vh - 120px);
  padding-bottom: 72px;
}

.audit-header {
  padding: 4px 0 20px;
  background: transparent;
  border: none;
}

.audit-back {
  appearance: none;
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  padding: 0 0 12px;
  cursor: pointer;
}

.audit-back:hover {
  color: var(--ink);
}

.audit-header h3 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--ink);
}

.audit-subtitle {
  margin: 8px 0 0;
  max-width: 720px;
  color: #8c8c8c;
  font-size: 13px;
  line-height: 1.5;
}

.audit-toolbar-card {
  margin-bottom: 0;
  border: 1px solid #f0f0f0;
  border-radius: 8px 8px 0 0;
  background: #fff;
  overflow: hidden;
}

.audit-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 16px;
  border-bottom: 1px solid #f0f0f0;
}

.audit-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  border-bottom: none;
}

.audit-filter-tab {
  appearance: none;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #595959;
  padding: 14px 16px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.audit-filter-tab small {
  margin-left: 6px;
  color: #8c8c8c;
  font-size: 12px;
}

.audit-filter-tab.is-active {
  color: #1677ff;
  background: #e6f4ff;
  border-bottom-color: #1677ff;
}

.audit-toolbar-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}

.audit-search {
  width: min(240px, 100%);
}

.audit-table-card {
  border: 1px solid #f0f0f0;
  border-top: none;
  border-radius: 0 0 8px 8px;
  background: #fff;
  overflow: hidden;
}

.audit-table-scroll {
  overflow: auto;
  max-height: min(62vh, 720px);
}

.audit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.audit-table th,
.audit-table td {
  padding: 14px 16px;
  border-bottom: 1px solid #f0f0f0;
  text-align: left;
  vertical-align: middle;
}

.audit-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #fafafa;
  color: #595959;
  font-weight: 500;
  white-space: nowrap;
}

.audit-table tr.is-selected td {
  background: #e6f4ff;
}

.audit-table tr.is-approved td {
  background: #f6ffed;
}

.audit-table tr.is-rejected td {
  background: #fff2f0;
}

.audit-cell-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.45;
  color: var(--ink);
}

.audit-price {
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

.audit-status {
  font-size: 13px;
  font-weight: 500;
}

.audit-status.is-pending {
  color: #1677ff;
}

.audit-status.is-approved {
  color: #389e0d;
}

.audit-status.is-rejected {
  color: #cf1322;
}

.audit-category {
  color: #595959;
  font-size: 13px;
}

.audit-action.is-view {
  color: #595959;
}

.audit-footer {
  position: sticky;
  bottom: 0;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 16px;
  padding: 12px 16px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fff;
}

.audit-footer-left {
  font-size: 13px;
  color: #595959;
}

.audit-footer-center {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.audit-footer-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}

.audit-meta {
  margin: 10px 0 0;
  font-size: 12px;
}

.audit-template-panel {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px;
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: linear-gradient(180deg, rgba(255, 248, 235, 0.7), var(--surface));
}

.audit-template-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.audit-template-head h4 {
  margin: 0;
  font-size: 15px;
}

.audit-template-badge {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 153, 0, 0.14);
  color: #b45309;
  font-size: 11px;
}

.audit-template-intro {
  margin: 6px 0 10px;
  font-size: 12px;
  line-height: 1.5;
}

.audit-template-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.audit-template-select {
  min-width: 280px;
}

.audit-template-reason {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--ink-2);
}

.audit-template-meta {
  margin: 0;
  font-size: 12px;
}

.audit-template-link {
  font-size: 13px;
  color: var(--brand);
}

.audit-template-chip {
  display: block;
  margin-top: 4px;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(255, 153, 0, 0.12);
  color: #9a6700;
  font-size: 11px;
  line-height: 1.3;
}

.audit-header-metrics,
.audit-quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.audit-metric {
  min-width: 72px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--gray3);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.audit-metric strong {
  font-size: 15px;
  line-height: 1;
}

.audit-metric span {
  font-size: 11px;
  color: var(--muted);
}

.audit-metric.is-done {
  border-color: #b7ebc6;
  background: #f3fbf5;
}

.audit-metric.is-warn {
  border-color: #f0d58a;
  background: #fffdf5;
}

.audit-quick-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: var(--gray2);
}

.audit-quick-images {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.audit-image-hint {
  font-size: 12px;
}

.audit-ai-progress {
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: var(--surface);
  padding: 0 16px 12px;
}

.audit-ai-progress summary {
  cursor: pointer;
  padding: 12px 0;
  font-weight: 600;
  list-style: none;
}

.audit-ai-progress summary::-webkit-details-marker {
  display: none;
}

.audit-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.audit-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  border-bottom: 1px solid var(--line);
}

.audit-filter-tab {
  appearance: none;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--ink-2);
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.audit-filter-tab small {
  margin-left: 4px;
  color: var(--muted);
}

.audit-filter-tab.is-active {
  color: var(--accent-text);
  border-bottom-color: var(--accent);
}

.audit-toolbar-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.audit-search {
  width: min(280px, 100%);
}

.audit-field-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 12px;
  color: var(--ink-2);
  margin: 0 0 12px;
}

.audit-ecosystem-panel {
  margin-bottom: 14px;
}

.ecosystem-brief-compact .ecosystem-brief-steps,
.ecosystem-brief-compact .ecosystem-golden,
.ecosystem-brief-compact .ecosystem-kw-tiers {
  display: none;
}

.audit-table .col-row-num {
  width: 36px;
  text-align: center;
  color: var(--muted);
}

.audit-table .col-field {
  min-width: 120px;
  max-width: 220px;
}

.audit-table .col-field.is-required-col {
  background: #fff7f7;
}

.audit-table .col-field.is-score-col {
  background: #fffdf5;
}

.audit-table th.col-field.is-required-col {
  background: #fef2f2;
}

.audit-table th.col-field.is-score-col {
  background: #fffbeb;
}

.audit-table .need {
  margin-left: 4px;
  color: #dc2626;
  font-size: 10px;
  font-weight: 700;
}

.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  margin-right: 6px;
}

.legend-dot.is-required {
  background: #dc2626;
}

.legend-dot.is-score {
  background: #d97706;
}

.audit-table-card {
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: var(--surface);
  overflow: hidden;
}

.audit-table-scroll {
  overflow: auto;
  max-height: min(62vh, 720px);
}

.audit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.audit-table th,
.audit-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: middle;
}

.audit-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f8fafc;
  color: var(--ink-2);
  font-weight: 600;
  white-space: nowrap;
}

.audit-table tr.is-selected td {
  background: var(--accent-wash);
}

.audit-table tr.is-issue td {
  background: #fffdf5;
}

.audit-table tr.is-approved td {
  background: #f6ffed;
}

.audit-table tr.is-rejected td {
  background: #fff5f5;
}

.audit-product {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 180px;
}

.audit-product-thumb {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  background: var(--gray3);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-weight: 600;
  color: var(--muted);
}

.audit-product-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.audit-product-meta {
  display: grid;
  gap: 2px;
}

.audit-product-meta b {
  font-size: 13px;
  line-height: 1.3;
}

.audit-product-meta span {
  font-size: 11px;
  color: var(--muted);
}

.audit-category {
  font-size: 12px;
  color: var(--ink-2);
}

.audit-attr-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-width: 220px;
}

.audit-chip {
  display: inline-flex;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10px;
  line-height: 1.4;
}

.audit-chip.is-required {
  background: #fee2e2;
  color: #991b1b;
}

.audit-chip.is-score {
  background: #fef3c7;
  color: #92400e;
}

.audit-image-strip {
  display: flex;
  align-items: center;
  gap: 4px;
}

.audit-image-thumb {
  width: 34px;
  height: 34px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--gray3);
  border: 1px solid var(--line);
}

.audit-image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.audit-image-thumb.is-empty {
  opacity: 0.45;
}

.audit-image-more {
  font-size: 11px;
  color: var(--muted);
  padding-left: 2px;
}

.audit-image-more.is-warn {
  color: #9a6700;
}

.audit-badge {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  background: var(--gray3);
  color: var(--ink-2);
  white-space: nowrap;
}

.audit-badge.is-approved {
  background: #dafbe1;
  color: #1a7f37;
}

.audit-badge.is-rejected {
  background: #ffebe9;
  color: #cf222e;
}

.audit-badge.is-warn {
  background: #fff8c5;
  color: #9a6700;
}

.audit-badge.is-ready {
  background: #dbeafe;
  color: #1d4ed8;
}

.audit-row-actions {
  display: flex;
  gap: 6px;
}

.audit-action {
  width: 28px;
  height: 28px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}

.audit-action.is-approve {
  color: #1a7f37;
}

.audit-action.is-reject {
  color: #cf222e;
}

.audit-footer {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(8px);
}

.audit-footer-left,
.audit-footer-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.audit-footer-center {
  font-size: 12px;
}

.audit-drawer {
  display: grid;
  gap: 18px;
}

.audit-drawer-section h4 {
  margin: 0 0 10px;
  font-size: 14px;
}

.audit-drawer-section label {
  display: block;
  margin: 8px 0 4px;
  font-size: 12px;
  color: var(--muted);
}

.audit-drawer-grid {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 8px 12px;
  align-items: center;
}

.audit-drawer-field + .audit-drawer-field {
  margin-top: 10px;
}

.audit-drawer-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.audit-infer-hint {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
}

@media (max-width: 960px) {
  .audit-header {
    flex-direction: column;
  }

  .audit-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .audit-footer-right {
    justify-content: space-between;
  }
}
</style>
