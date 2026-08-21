<template>
  <div class="page">
    <div class="page-head">
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

      <div class="flow-bar">
        <el-button @click="backToChooser">新建任务</el-button>
        <span class="muted">{{ currentTitle }} · 做到一半会自动记下，关掉也能回来</span>
        <el-button text @click="dropCurrent">不要这条了</el-button>
      </div>

      <FishboneSteps v-model="docStep" :steps="docSteps" :reached="docReached" />

      <div v-if="docStep === 0" class="step-panel">
        <h3>选类目，生成智能填写表</h3>
        <p class="muted">选好叶子类目后，AI 会读取官方 schema 并规划你需要手填的列。</p>
        <div style="margin-top: 16px">
          <el-button type="primary" @click="openDocCategory">{{ doc.categoryName || smartPlan.category_name || "选择类目" }}</el-button>
        </div>

        <section v-if="smartPlanLoading" class="plan-panel plan-panel-loading">
          <p class="muted">AI 正在读取官方 schema 并规划填写列…</p>
        </section>

        <section v-else-if="doc.categoryId && smartPlan.column_count" class="plan-panel">
          <header class="plan-head">
            <span class="plan-badge">{{ smartPlan.planner === "llm" ? "AI 规划" : "规则规划" }}</span>
            <h4>{{ smartPlan.category_name || doc.categoryName }}</h4>
          </header>
          <div class="plan-stats">
            <div class="plan-stat">
              <strong>{{ smartPlan.schema_inventory?.total || "?" }}</strong>
              <span>官方 schema 字段</span>
            </div>
            <div class="plan-stat">
              <strong>{{ smartPlan.schema_inventory?.required_count || smartPlan.required_attr_count || 0 }}</strong>
              <span>其中必填</span>
            </div>
            <div class="plan-stat plan-stat-accent">
              <strong>{{ smartPlan.column_count }}</strong>
              <span>下载表需填列</span>
            </div>
          </div>
          <p v-if="plannerCoverageText" class="plan-coverage muted">{{ plannerCoverageText }}</p>
          <p v-if="smartPlan.reasoning" class="plan-reasoning">{{ smartPlan.reasoning }}</p>
          <div v-if="smartColumnLabels.length" class="plan-columns">
            <small>填写列</small>
            <div class="plan-column-tags">
              <span v-for="label in smartColumnLabels" :key="label" class="plan-tag">{{ label }}</span>
            </div>
          </div>
          <p v-if="smartPlan.tips" class="plan-tips">{{ smartPlan.tips }}</p>
        </section>
        <div class="toolbar" style="margin: 16px 0 12px">
          <el-button type="primary" :disabled="!doc.categoryId || smartPlanLoading" @click="downloadDocTemplate">
            下载智能填写表
          </el-button>
          <el-button :disabled="!doc.categoryId || smartPlanLoading" @click="refreshSmartPlan">重新规划</el-button>
        </div>
        <el-upload
          v-model:file-list="docFiles"
          :auto-upload="false"
          multiple
          :disabled="!doc.categoryId"
          accept=".xlsx,.xls,.xlsm,.csv,.txt,.md,.jpg,.jpeg,.png,.webp,.pdf"
          drag
        >
          <div style="padding: 22px 0">把填好的 xlsx / 报价单 / 目录拖到这里（可多文件）</div>
        </el-upload>
        <div class="step-actions" style="margin-top: 16px">
          <el-button type="primary" :loading="docGrid.loading" :disabled="!doc.categoryId || !docFiles.some((item) => item.raw)" @click="parseDocuments">
            解析并进入审核
          </el-button>
        </div>
      </div>

      <div v-else class="step-panel review-shell">
        <header class="review-hero">
          <div class="review-hero-main">
            <span class="review-kicker">批量上品 · 审核出图</span>
            <h3>{{ doc.categoryName || smartPlan.category_name || "未命名类目" }}</h3>
            <p class="review-hero-meta">
              {{ docGrid.row_count || docGrid.rows.length }} 个商品
              <span v-if="docGrid.source"> · {{ docGrid.source }}</span>
              <span v-if="docImageGenSummary"> · {{ docImageGenSummary }}</span>
            </p>
          </div>
          <div class="review-metrics">
            <div class="review-metric" :class="{ 'is-done': reviewStats.ready === reviewStats.total && reviewStats.total }">
              <strong>{{ reviewStats.ready }}/{{ reviewStats.total }}</strong>
              <span>价量齐</span>
            </div>
            <div class="review-metric" :class="{ 'is-done': reviewStats.imagesOk === reviewStats.total && reviewStats.total }">
              <strong>{{ reviewStats.imagesOk }}/{{ reviewStats.total }}</strong>
              <span>六图齐</span>
            </div>
            <div class="review-metric" :class="{ 'is-done': reviewStats.copyOk === reviewStats.total && reviewStats.total }">
              <strong>{{ reviewStats.copyOk }}/{{ reviewStats.total }}</strong>
              <span>文案齐</span>
            </div>
            <div class="review-metric" :class="{ 'is-warn': reviewStats.issueCount > 0 }">
              <strong>{{ reviewStats.issueCount }}</strong>
              <span>待改</span>
            </div>
            <div class="review-metric">
              <strong>{{ reviewStats.selected }}</strong>
              <span>已选</span>
            </div>
          </div>
          <div class="review-hero-actions">
            <el-button @click="downloadDocTemplate">下载填写表</el-button>
            <el-button @click="docStep = 0">重新导入</el-button>
          </div>
        </header>

        <el-alert
          v-for="warning in docGrid.warnings || []"
          :key="warning"
          type="warning"
          :title="warning"
          :closable="false"
          class="review-alert"
        />

        <section class="review-panel">
          <div class="review-panel-top">
            <div class="review-filters" role="tablist" aria-label="筛选商品行">
              <button
                v-for="item in reviewFilterOptions"
                :key="item.id"
                type="button"
                class="review-filter-pill"
                :class="{ 'is-active': reviewFilter === item.id }"
                @click="reviewFilter = item.id"
              >
                {{ item.label }}
                <small>{{ item.count }}</small>
              </button>
            </div>
            <button type="button" class="review-guide-toggle" @click="showReviewGuide = !showReviewGuide">
              {{ showReviewGuide ? "收起要点" : "审核要点" }}
            </button>
          </div>

          <div v-if="showReviewGuide && reviewChecklist.length" class="review-guide">
            <article v-for="item in reviewChecklist" :key="item.id" class="review-guide-item">
              <b>{{ item.label }}</b>
              <span>{{ item.hint }}</span>
            </article>
          </div>

          <el-tabs v-model="reviewOpsTab" class="review-tabs">
            <el-tab-pane label="选择" name="select">
              <div class="review-tab-body">
                <p class="review-tab-note">先勾选要批量处理的行，再切到其他标签执行操作。</p>
                <div class="review-tab-actions">
                  <el-checkbox v-model="docGrid.selectAll" @change="toggleSelectAll">全选当前列表</el-checkbox>
                  <el-button @click="invertDocSelection">反选</el-button>
                  <el-button @click="clearDocSelection">取消选择</el-button>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane label="文案" name="copy">
              <div class="review-tab-body">
                <div class="review-tab-actions">
                  <el-button :loading="docGrid.regenerating" type="primary" @click="regenCopyForSelection">AI 重写选中</el-button>
                  <el-button :loading="docGrid.regenerating" @click="regenCopyForAll">全部重写</el-button>
                  <el-button @click="clearCopyForSelection">清空选中</el-button>
                  <el-button @click="clearCopyForAll">清空全部</el-button>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane label="价量" name="trade">
              <div class="review-tab-body">
                <div class="review-tab-actions">
                  <el-button type="primary" @click="batchSetField('price')">批量改价</el-button>
                  <el-button @click="batchSetField('moq')">批量改起订量</el-button>
                  <el-button v-if="hasBrandColumn" @click="batchSetField('brand')">批量改品牌</el-button>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane label="图片" name="images">
              <div class="review-tab-body">
                <div class="review-tab-actions">
                  <el-button :loading="docGrid.generating" type="primary" @click="generateImagesForSelection">选中行出图</el-button>
                  <el-button :loading="docGrid.generating" @click="generateImagesForAll">全部出图</el-button>
                  <el-button :loading="docGrid.generating" @click="refreshGridImages">刷新状态</el-button>
                  <el-upload
                    v-model:file-list="excelImages"
                    :auto-upload="false"
                    multiple
                    accept="image/*"
                    :show-file-list="false"
                  >
                    <el-button>按货号补传</el-button>
                  </el-upload>
                </div>
                <p class="review-tab-note">图片命名如 SKU-1001.jpg。成稿时 {{ excelGoHint }}</p>
                <div class="review-policy-row">
                  <label>有图</label>
                  <el-radio-group v-model="excel.photoPolicy" size="small">
                    <el-radio-button value="keep">原图</el-radio-button>
                    <el-radio-button value="complete">补位</el-radio-button>
                    <el-radio-button value="boost">重画</el-radio-button>
                  </el-radio-group>
                  <label>没图</label>
                  <el-radio-group v-model="excel.emptyPolicy" size="small">
                    <el-radio-button value="draw">套图</el-radio-button>
                    <el-radio-button value="skip">跳过</el-radio-button>
                  </el-radio-group>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane label="表格" name="table">
              <div class="review-tab-body">
                <div class="review-tab-actions">
                  <el-button type="primary" @click="addDocRow">加一行</el-button>
                  <el-button @click="duplicateSelectedRows">复制选中</el-button>
                  <el-button type="danger" plain @click="deleteSelectedRows">删除选中</el-button>
                  <el-button :loading="docGrid.checking" @click="recheckDocGrid">重新校验</el-button>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </section>

        <section class="review-grid-card">
          <div class="review-grid-head">
            <div>
              <b>商品明细</b>
              <span class="muted">显示 {{ filteredDocRowViews.length }}/{{ docGrid.rows.length }} 行</span>
            </div>
            <span class="muted">可直接改单元格</span>
          </div>
          <div class="doc-grid-wrap review-grid-scroll">
            <table class="doc-grid doc-grid-wide review-grid">
              <thead>
                <tr>
                  <th class="col-check"></th>
                  <th>#</th>
                  <th class="col-status">状态</th>
                  <th class="col-slots">商品图 ×6</th>
                  <th v-for="col in docDataColumns" :key="col.id">
                    {{ col.label }}<span v-if="col.required" class="need">必填</span>
                  </th>
                  <th class="col-row-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="view in filteredDocRowViews"
                  :key="view.row.line || view.index"
                  :class="{ 'is-issue': rowHasIssues(view.row), 'is-selected': view.row._selected }"
                >
                  <td class="col-check">
                    <el-checkbox v-model="view.row._selected" />
                  </td>
                  <td>{{ view.index + 1 }}</td>
                  <td class="col-status">
                    <span v-if="rowHasIssues(view.row)" class="row-badge is-warn">待改</span>
                    <span v-else-if="rowReady(view.row) && rowImageCount(view.row) >= 6" class="row-badge is-ok">可成稿</span>
                    <span v-else class="row-badge">编辑中</span>
                  </td>
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
                  <td v-for="col in docDataColumns" :key="`${view.index}-${col.id}`">
                    <el-input
                      v-if="col.kind === 'textarea'"
                      v-model="view.row[col.id]"
                      type="textarea"
                      :rows="col.id === 'title' ? 2 : 1"
                      size="small"
                    />
                    <el-select
                      v-else-if="col.options?.length"
                      v-model="view.row[col.id]"
                      filterable
                      clearable
                      placeholder="选"
                      size="small"
                      style="width: 100%"
                    >
                      <el-option v-for="opt in col.options" :key="opt.value" :label="opt.label" :value="opt.label" />
                    </el-select>
                    <el-input v-else v-model="view.row[col.id]" size="small" />
                  </td>
                  <td class="col-row-actions">
                    <el-button text @click="duplicateDocRow(view.index)">复制</el-button>
                    <el-button text @click="generateImagesForRow(view.row)">出图</el-button>
                    <el-button text type="danger" @click="removeDocRow(view.index)">删</el-button>
                  </td>
                </tr>
                <tr v-if="!filteredDocRowViews.length">
                  <td :colspan="docDataColumns.length + 5" class="review-empty">
                    当前筛选下没有行。<el-button text @click="reviewFilter = 'all'">显示全部</el-button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <details v-if="docGrid.row_issues?.length" class="review-issues" :open="reviewStats.issueCount > 0">
          <summary>
            <span>成稿前先看这几行（{{ docGrid.row_issues.length }}）</span>
            <el-button text size="small" @click.stop="reviewFilter = 'issues'">只看有问题行</el-button>
          </summary>
          <ul>
            <li v-for="(issue, idx) in docGrid.row_issues.slice(0, 16)" :key="idx">
              <span :class="['dot', issue.level]"></span>
              第 {{ issue.line }} 行 {{ issue.sku }}：{{ issue.message }}
            </li>
          </ul>
        </details>

        <footer class="review-actionbar">
          <div class="review-actionbar-main">
            <el-button
              type="primary"
              size="large"
              :loading="docGrid.loading"
              :disabled="!docGrid.rows.length || !store.shopId || !doc.categoryId"
              @click="importDocRows"
            >
              批量成稿（{{ docGrid.rows.length }} 个）
            </el-button>
            <p class="muted">每行需 6 张图或已生成套图。成稿后进草稿审，5.0 分且审过才能发。</p>
          </div>
        </footer>

        <div v-if="doc.batch" class="review-batch-progress">
          <p>
            共 {{ doc.batch.count }} 个商品，已成稿 {{ docProgress.done }}/{{ doc.batch.count }}。
            <template v-if="docProgress.complete">
              待审 {{ docProgress.pending || 0 }} · 待改 {{ docProgress.counts?.red || 0 }} · 已审可发 {{ docProgress.ready || 0 }}。
            </template>
          </p>
          <el-progress :percentage="docPercent" :stroke-width="10" />
          <div style="margin-top: 12px">
            <el-button type="primary" :disabled="!docProgress.complete" @click="goDocBatchDrafts('pending')">去审这一批</el-button>
          </div>
        </div>
      </div>
    </template>

    <CategoryPicker v-model="categoryBrowser" @pick="pickCategory" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import CategoryPicker from "../components/CategoryPicker.vue";
import FishboneSteps from "../components/FishboneSteps.vue";
import { api } from "../api";
import { store } from "../store";

const router = useRouter();
const route = useRoute();
const sessionId = ref("");
const sessionBooting = ref(true);
const openSessions = ref([]);
const currentTitle = ref("");
const restoring = ref(false);
const docStep = ref(0);
const docReached = ref(0);
const docSteps = [
  { key: "setup", label: "智能表下载填写" },
  { key: "grid", label: "审核出图成稿" },
];
const DEFAULT_REVIEW_CHECKLIST = [
  { id: "category", label: "类目一致", hint: "整批共用所选叶子类目，行内属性选项合法" },
  { id: "copy", label: "标题关键词", hint: "英文标题靠前放核心词；1～3 个询盘向关键词" },
  { id: "trade", label: "价量红线", hint: "单价、起订量由你定，AI 不会改" },
  { id: "attrs", label: "必填属性", hint: "下拉必须来自官方选项，不能手打 Other" },
  { id: "images", label: "六张图", hint: "实拍可上传；缺图可并发出图，生成图成稿后标黄" },
  { id: "quality", label: "信息分 5.0", hint: "成稿后本地预估六桶，人审过才能发" },
];
const reviewFilter = ref("all");
const reviewOpsTab = ref("select");
const showReviewGuide = ref(false);
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
const doc = reactive({
  categoryId: "",
  categoryName: "",
  batch: null,
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
const smartPlan = ref({ columns: [], column_count: 0, reasoning: "", tips: "", planner: "rules", covered_by_shop: [], covered_by_template: [], ai_fills: [] });
const smartPlanLoading = ref(false);
const categoryBrowser = ref(false);

const coreFillIds = new Set(["sku", "price", "moq", "images", "brand", "name", "note"]);
const smartColumnLabels = computed(() => (smartPlan.value.columns || []).map((col) => col.label).filter(Boolean));
const otherSessions = computed(() => openSessions.value.filter((item) => item.id !== sessionId.value));
const plannerCoverageText = computed(() => {
  const input = smartPlan.value.planner_input;
  const inv = smartPlan.value.schema_inventory;
  if (!inv?.total) return "";
  if (smartPlan.value.planner === "llm" && input) {
    return `AI 已读取官方 schema 全部 ${input.schema_fields_sent} 个字段名（必填 ${input.required_fields_sent}、可选 ${input.optional_fields_sent}），并结合 ${input.candidate_columns_sent} 个候选列（含下拉选项）规划出 ${smartPlan.value.column_count} 列。英文标题/关键词在审核阶段填写，不在下载表里。`;
  }
  if (smartPlan.value.planner === "llm") {
    return `AI 已读取官方 schema 全部 ${inv.total} 个字段名（必填 ${inv.required_count}），规划出 ${smartPlan.value.column_count} 列。`;
  }
  return `按规则从官方必填项生成 ${smartPlan.value.column_count} 列（当前未启用 AI，使用规则规划）。`;
});
const excelImageMode = computed(() => `${excel.photoPolicy || "complete"}_${excel.emptyPolicy || "draw"}`);
const excelImageUploadHint = computed(() => {
  if (excel.photoPolicy === "boost") {
    return "有本地图或表里的链接都只当认货参考。没图的行看下面第二条。";
  }
  if (excel.emptyPolicy === "skip") {
    return "有本地图就拖进来，按货号命名。对不上的行会跳过。";
  }
  return "有本地图就拖进来，按货号命名。表里写了链接也不用再传。没对上的行按品名画套图。";
});
const excelGoHint = computed(() => {
  const photoText = {
    keep: "有图的原图上架",
    complete: "有图的原图留下并补转化位",
    boost: "有图的当参考重画套图",
  }[excel.photoPolicy] || "有图的按你选的规则处理";
  const emptyText = excel.emptyPolicy === "skip" ? "没图的跳过" : "没图的按品名画套图并标黄";
  return `${photoText}，${emptyText}。后台一条一条过。`;
});
const docPercent = computed(() => {
  if (!doc.batch?.count) return 0;
  return Math.min(100, Math.round((docProgress.value.done / doc.batch.count) * 100));
});
const docDataColumns = computed(() => docGrid.columns.filter((col) => col.id !== "images"));
const docSelectedCount = computed(() => docGrid.rows.filter((row) => row._selected).length);
const hasBrandColumn = computed(() => docGrid.columns.some((col) => col.id === "brand"));
const reviewChecklist = computed(() => {
  if (smartPlan.value.review_checklist?.length) return smartPlan.value.review_checklist;
  return DEFAULT_REVIEW_CHECKLIST;
});
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
const filteredDocRowViews = computed(() =>
  docGrid.rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => {
      switch (reviewFilter.value) {
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
    }),
);
const reviewFilterOptions = computed(() => [
  { id: "all", label: "全部", count: reviewStats.value.total },
  { id: "issues", label: "有问题", count: reviewStats.value.issueCount },
  { id: "no_images", label: "缺图", count: reviewStats.value.total - reviewStats.value.imagesOk },
  { id: "no_copy", label: "缺文案", count: reviewStats.value.total - reviewStats.value.copyOk },
  { id: "not_ready", label: "价量未齐", count: reviewStats.value.total - reviewStats.value.ready },
  { id: "selected", label: "已选", count: reviewStats.value.selected },
]);
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
  if (running) return `套图并发生成中 ${running}/${rows.length} 行`;
  if (ready === rows.length) return `6 张图已齐 ${ready}/${rows.length} 行`;
  return `待出图 ${rows.length - ready} 行（进入审核后自动开始）`;
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
    openSessions.value = (data.sessions || []).filter((item) =>
      ["doc", "excel", "full"].includes(item.path),
    );
  } catch {
    openSessions.value = [];
  }
}

async function persistSession() {
  if (!sessionId.value || restoring.value) return;
  try {
    const saved = await api.saveFeedSession(sessionId.value, {
      shop_id: store.shopId || "",
      step: currentStep(),
      reached: currentReached(),
      payload: sessionPayload(),
    });
    currentTitle.value = saved.title || currentTitle.value;
  } catch {
    /* keep typing even if save is slow */
  }
}



function applySession(session) {
  restoring.value = true;
  sessionId.value = session.id;
  currentTitle.value = session.title || session.path_label;
  const payload = session.payload || {};
  if (payload.excel) {
    applyExcelImageMode(payload.excel.imageMode, payload.excel.photoPolicy, payload.excel.emptyPolicy);
  }
  if (payload.doc) {
    doc.categoryId = payload.doc.categoryId || "";
    doc.categoryName = payload.doc.categoryName || payload.categoryName || "";
    doc.batch = payload.doc.batch || null;
    docGrid.columns = payload.doc.columns || [];
    docGrid.rows = normalizeDocRows(payload.doc.rows || []);
    docGrid.row_issues = payload.doc.row_issues || [];
    docGrid.warnings = payload.doc.warnings || [];
    docGrid.row_count = payload.doc.row_count || docGrid.rows.length;
    docGrid.ready_count = payload.doc.ready_count || 0;
    docGrid.source = payload.doc.source || "";
    if (payload.doc.smartPlan?.columns?.length) {
      smartPlan.value = payload.doc.smartPlan;
    }
    applyExcelImageMode(payload.doc.imageMode, payload.doc.photoPolicy, payload.doc.emptyPolicy);
    const names = payload.doc.uploadNames || [];
    docFiles.value = names.map((name) => ({ name, status: "success" }));
  } else {
    doc.categoryId = "";
    doc.categoryName = "";
    doc.batch = null;
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
}

async function startPath() {
  try {
    const created = await api.createFeedSession({ path: "doc", shop_id: store.shopId || "" });
    docStep.value = 0;
    docReached.value = 0;
    doc.categoryId = "";
    doc.categoryName = "";
    doc.batch = null;
    docGrid.columns = [];
    docGrid.rows = [];
    docGrid.row_issues = [];
    docGrid.warnings = [];
    docGrid.row_count = 0;
    docGrid.ready_count = 0;
    docGrid.source = "";
    docFiles.value = [];
    smartPlan.value = { columns: [], column_count: 0, reasoning: "", tips: "", planner: "rules", covered_by_shop: [], covered_by_template: [], ai_fills: [] };
    applySession(created);
    router.replace({ query: { session: created.id } });
    await loadOpenSessions();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function resumeSession(id) {
  try {
    const session = await api.feedSession(id);
    applySession(session);
    router.replace({ query: { session: id } });
    if (doc.batch?.batch_id) {
      clearInterval(docTimer);
      docTimer = setInterval(pollDoc, 3000);
      await pollDoc();
    }
    if (doc.categoryId) {
      await loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName });
      ensureGridPolling();
    }
  } catch (error) {
    const msg = String(error.message || "");
    if (msg.includes("不在了")) {
      ElMessage.warning("这条做到一半的记录已失效，请新建批量任务");
      sessionId.value = "";
      router.replace({ query: {} });
      await loadOpenSessions();
      return;
    }
    ElMessage.error(error.message);
  }
}

async function dropSession(id) {
  try {
    await api.dropFeedSession(id);
    if (sessionId.value === id) {
      sessionId.value = "";
      router.replace({ query: {} });
    }
    await loadOpenSessions();
  } catch (error) {
    ElMessage.error(error.message);
  }
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
    if (route.query.session) {
      await resumeSession(String(route.query.session));
    } else {
      await startPath();
    }
  } finally {
    sessionBooting.value = false;
  }
}

onMounted(async () => {
  try {
    await store.ensureShops();
  } catch {
    /* shop list loads again when user opens category picker */
  }
  await bootSession();
});

let saveTimer = null;
watch(
  () => [excel.photoPolicy, excel.emptyPolicy],
  () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persistSession, 400);
  },
);
watch(
  () => docStep.value,
  (step) => {
    if (step === 1) autoStartReviewImages();
  },
);
watch(
  () => [docStep.value, doc.categoryId, doc.categoryName, docGrid.rows],
  () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persistSession, 500);
  },
  { deep: true },
);




async function loadSmartPlan(override = null) {
  const categoryId = override?.categoryId ?? doc.categoryId ?? "";
  const categoryName = override?.categoryName ?? doc.categoryName ?? "";
  if (!store.shopId || !categoryId) return;
  smartPlanLoading.value = true;
  try {
    smartPlan.value = await api.excelSmartPlan({
      shop_id: store.shopId,
      category_id: categoryId,
      category_name: categoryName,
    });
    docGrid.columns = smartPlan.value.columns || [];
  } catch (error) {
    const msg = String(error.message || "");
    if (msg.includes("店铺不存在")) {
      await store.ensureShops();
      if (store.shopId) {
        smartPlan.value = await api.excelSmartPlan({
          shop_id: store.shopId,
          category_id: categoryId,
          category_name: categoryName,
        });
        docGrid.columns = smartPlan.value.columns || [];
        return;
      }
    }
    throw error;
  } finally {
    smartPlanLoading.value = false;
  }
}

async function refreshSmartPlan() {
  if (!doc.categoryId) {
    ElMessage.warning("先选叶子类目");
    return;
  }
  try {
    await loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName });
    ElMessage.success(`已更新：需填 ${smartPlan.value.column_count || 0} 列`);
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
  persistSession();
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
    }
    await persistSession();
  } catch {
    clearInterval(gridPollTimer);
    gridPollTimer = null;
  }
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
  if (!docGrid.rows.length) return;
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
    if (result.errors?.length) ElMessage.warning(result.errors[0]);
    ensureGridPolling();
    await persistSession();
    if (!silent) {
      ElMessage.success(lines?.length ? "已开始为选中行出图" : "已开始为全部商品出图");
    }
  } catch (error) {
    if (!silent) ElMessage.error(error.message);
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

async function regenCopyForRows(lines) {
  if (!docGrid.rows.length) return;
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
    if (result.errors?.length) ElMessage.warning(result.errors[0]);
    await persistSession();
    ElMessage.success(lines?.length ? "已重写选中行文案" : "已重写全部文案");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    docGrid.regenerating = false;
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
  if (!docFiles.value.some((item) => item.raw)) {
    ElMessage.warning("先上传资料");
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
  docFiles.value.forEach((item) => item.raw && body.append("files", item.raw));
  docGrid.loading = true;
  try {
    const result = await api.excelDocParse(body);
    docGrid.columns = result.columns || smartPlan.value.columns || [];
    if (result.download_columns?.length) {
      smartPlan.value = { ...smartPlan.value, download_columns: result.download_columns };
    }
    docGrid.rows = normalizeDocRows(result.rows || []);
    docGrid.row_issues = result.row_issues || [];
    docGrid.warnings = result.warnings || [];
    docGrid.row_count = result.row_count || docGrid.rows.length;
    docGrid.ready_count = result.ready_count || 0;
    docGrid.source = result.source || "";
    await persistSession();
    advanceDoc(1);
    ElMessage.success(`识别到 ${docGrid.row_count} 个商品，已进入审核；套图正在后台并发生成`);
    await autoStartReviewImages();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    docGrid.loading = false;
  }
}

async function recheckDocGrid() {
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
    ElMessage.success(`校验完成：${docGrid.ready_count}/${docGrid.row_count} 个价量齐`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    docGrid.checking = false;
  }
}

function addDocRow() {
  const row = { line: docGrid.rows.length + 2, _selected: false, image_slots: DEFAULT_IMAGE_SLOTS.map((slot) => ({ ...slot })) };
  docGrid.columns.length ? docGrid.columns : smartPlan.value.columns || [].forEach((col) => {
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
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("category_id", doc.categoryId);
  body.append("session_id", sessionId.value);
  body.append("image_mode", excelImageMode.value);
  if (smartPlan.value.columns?.length) {
    body.append("columns", JSON.stringify(smartPlan.value.columns));
  }
  body.append("rows", JSON.stringify(docGrid.rows));
  excelImages.value.forEach((item) => item.raw && body.append("images", item.raw));
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

function downloadDocTemplate() {
  if (!doc.categoryId) {
    ElMessage.warning("先选叶子类目");
    return;
  }
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  window.location.href = api.excelSmartTemplateUrl({
    categoryId: doc.categoryId,
    shopId: store.shopId,
    categoryName: doc.categoryName || smartPlan.value.category_name,
  });
}


async function pickCategory(node) {
  doc.categoryId = node.category_id;
  doc.categoryName = node.path_label || node.label || node.name || node.cn_name || "";
  try {
    await store.ensureShops();
    await loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName });
    ElMessage.success(`已选「${smartPlan.value.category_name || doc.categoryName}」，可下载智能填写表`);
    await persistSession();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

onUnmounted(() => {
  clearInterval(docTimer);
  clearInterval(gridPollTimer);
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
.plan-head {
  display: flex;
  align-items: center;
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
  margin: 0;
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
</style>
