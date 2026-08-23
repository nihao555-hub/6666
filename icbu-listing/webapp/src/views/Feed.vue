<template>
  <div class="page">
    <div v-if="docStep !== 1" class="page-head">
      <h2>批量上品</h2>
    </div>

    <el-alert
      v-if="!store.shopId"
      type="warning"
      show-icon
      :closable="false"
      title="先登录店铺"
      style="margin-bottom: 14px"
    />

    <div v-if="sessionBooting" class="boot-panel">
      <p class="muted">加载中…</p>
    </div>

    <template v-else-if="sessionId">
      <div v-if="otherSessions.length && docStep !== 1" class="resume-inline">
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
        <span class="muted">{{ currentTitle }}</span>
        <el-button text @click="dropCurrent">删除</el-button>
      </div>

      <FishboneSteps v-if="docStep !== 1" v-model="docStep" :steps="docSteps" :reached="docReached" />

      <div v-if="docStep === 0 && !awaitingReviewAssist && !docGrid.loading && !reviewAssistRunning" class="step-panel flow-shell">
        <!-- 1 商品图 -->
        <section class="flow-step" :class="{ 'is-done': imageSetupMode !== 'pending' }">
          <header class="flow-step-head">
            <span class="flow-step-badge">1</span>
            <div class="flow-step-titles">
              <h3>商品图</h3>
              <p v-if="imageSetupMode === 'confirmed'">已选 {{ confirmedPlanImageCount }} 张</p>
              <p v-else-if="imageSetupMode === 'skipped'">已跳过，按类目生成表头</p>
              <p v-else>拖入图片或从图片银行选，然后点确定</p>
            </div>
            <button v-if="imageSetupMode !== 'pending'" type="button" class="link-btn" @click="resetImageSetup">更改</button>
          </header>
          <div v-if="imageSetupMode === 'pending'" class="flow-step-body">
            <div class="flow-compact-actions">
              <el-button :disabled="!store.shopId" :loading="photobankLoading" @click="openPhotobank">图片银行</el-button>
              <el-button plain @click="pickImageFolder">本地文件夹</el-button>
            </div>
            <section v-if="photobankOpen" class="photobank-panel">
              <div v-if="photobankLoading" class="muted">加载中…</div>
              <div v-else-if="!photobankImages.length" class="muted">图片银行为空</div>
              <div v-else class="photobank-grid">
                <button
                  v-for="item in photobankImages"
                  :key="item.id || item.url"
                  type="button"
                  class="photobank-item"
                  :class="{ 'is-selected': photobankDraftIds.has(item.id || item.url) }"
                  @click="togglePhotobankDraft(item)"
                >
                  <img :src="item.url" :alt="item.file_name || 'bank'" loading="lazy" />
                </button>
              </div>
              <div v-if="photobankOpen && photobankImages.length" class="photobank-actions">
                <el-button @click="cancelPhotobankPicker">取消</el-button>
                <el-button type="primary" @click="confirmPhotobankPicker">确定（{{ photobankDraftIds.size }}）</el-button>
              </div>
            </section>
            <div class="upload-drop-zone" @dragover.prevent @dragenter.prevent @drop.prevent="onDropImageFiles">
              <input ref="folderInput" type="file" webkitdirectory multiple accept="image/*" class="hidden-folder-input" @change="onFolderPick" />
              <el-upload
                v-model:file-list="docImageFiles"
                :auto-upload="false"
                multiple
                accept=".jpg,.jpeg,.png,.webp,.gif"
                drag
                @change="onDocImageFilesChange"
              >
                <div class="upload-drop-inner">
                  <p>拖入商品图片</p>
                </div>
              </el-upload>
            </div>
            <div class="flow-compact-actions">
              <el-button type="primary" :disabled="!pendingPlanImageCount" @click="confirmPlanImages">
                确定选图{{ pendingPlanImageCount ? ` · ${pendingPlanImageCount} 张` : "" }}
              </el-button>
              <el-button text @click="skipPlanImages">跳过</el-button>
            </div>
          </div>
        </section>

        <!-- 2 类目 + 表头 -->
        <section class="flow-step" :class="{ 'is-done': Boolean(doc.categoryId && smartPlan.column_count), 'is-locked': !canPickCategory }">
          <header class="flow-step-head">
            <span class="flow-step-badge">2</span>
            <div class="flow-step-titles">
              <h3>选类目，生成填写表</h3>
              <p v-if="doc.categoryName">{{ doc.categoryName }} · {{ smartPlan.column_count || "—" }} 列</p>
              <p v-else-if="!canPickCategory">先完成上一步</p>
              <p v-else>选叶子类目，系统自动生成要填的列</p>
            </div>
            <el-button v-if="canPickCategory && !doc.categoryId" type="primary" size="small" @click="openDocCategory">选类目</el-button>
            <el-button v-else-if="doc.categoryId" text size="small" @click="openDocCategory">更换</el-button>
          </header>
          <div v-if="canPickCategory" class="flow-step-body">
            <div v-if="showSmartPlanTimeline" class="flow-loading">
              {{ smartPlanLoadingText }}
              <div class="flow-loading-bar"><span /></div>
            </div>
            <section v-else-if="smartPlanError" class="plan-panel plan-panel-error" style="margin: 0">
              <p>{{ smartPlanError }}</p>
              <el-button type="primary" :loading="smartPlanLoading" @click="refreshSmartPlan">重试</el-button>
            </section>
            <section v-else-if="doc.categoryId && smartPlan.column_count" class="ready-card">
              <div class="ready-card-head">
                <h4>{{ smartPlan.category_name || doc.categoryName }}</h4>
                <span class="plan-badge">{{ smartPlan.column_count }} 列</span>
              </div>
              <div v-if="smartColumnLabels?.length" class="ready-tags">
                <span v-for="label in smartColumnLabels" :key="label" class="ready-tag">{{ label }}</span>
              </div>
              <p class="ready-meta plan-flow-note">
                下载表 {{ smartPlan.column_count }} 列（你填写）
                <template v-if="smartPlanEvidenceCount">，含 {{ smartPlanEvidenceCount }} 个类目属性</template>
                <template v-if="smartPlanAiFillCount">；上传后 AI 补 {{ smartPlanAiFillCount }} 个官方字段</template>
                <template v-else-if="smartPlan.review_note">；{{ smartPlan.review_note }}</template>
              </p>
              <p v-if="habitsNeedsPick" class="ready-meta">
                推荐运费：{{ habitsPanel.shipping_recommendation?.label || "—" }}
              </p>
              <p v-else-if="habitsSummaryLine" class="ready-meta">{{ habitsSummaryLine }}</p>
              <div v-if="habitsNeedsPick" class="flow-compact-actions">
                <el-select v-model="habitsShippingPick" filterable style="flex: 1; min-width: 180px">
                  <el-option v-for="opt in habitsPanel.shipping_options || []" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <el-button type="primary" :loading="habitsApplying" @click="adoptHabitsRecommendation">确认运费</el-button>
              </div>
              <details v-if="smartPlan.tips || smartPlan.guarantee" class="flow-details">
                <summary>表头说明</summary>
                <p v-if="smartPlan.tips">{{ smartPlan.tips }}</p>
                <p v-if="smartPlan.guarantee">{{ smartPlan.guarantee }}</p>
              </details>
            </section>
          </div>
        </section>

        <!-- 3 下载 -->
        <section class="flow-step" :class="{ 'is-locked': !canDownloadTemplate }">
          <header class="flow-step-head">
            <span class="flow-step-badge">3</span>
            <div class="flow-step-titles">
              <h3>下载并填写表格</h3>
              <p>只需填价、量、货号和少量属性，其余 AI 补</p>
              <p v-if="confirmedPlanImageCount" class="flow-step-note">已选图会嵌进「图片」列</p>
            </div>
            <el-button
              type="primary"
              size="small"
              :disabled="!canDownloadTemplate || smartPlanLoading || docTemplateDownloading"
              :loading="docTemplateDownloading"
              @click="downloadDocTemplate"
            >
              下载
            </el-button>
          </header>
        </section>

        <!-- 4 上传解析 -->
        <section class="flow-step" :class="{ 'is-locked': !doc.categoryId }">
          <header class="flow-step-head">
            <span class="flow-step-badge">4</span>
            <div class="flow-step-titles">
              <h3>上传表格</h3>
              <p>填好后拖入，AI 自动补全文案和属性</p>
            </div>
          </header>
          <div v-if="doc.categoryId" class="flow-step-body">
            <div class="upload-drop-zone" @dragover.prevent @dragenter.prevent @drop.prevent="onDropDocFiles">
              <el-upload
                v-model:file-list="docSpreadsheetFiles"
                :auto-upload="false"
                multiple
                accept=".xlsx,.xls,.xlsm,.csv"
                drag
                @change="onDocSpreadsheetChange"
              >
                <div class="upload-drop-inner">
                  <p>拖入已填好的 Excel</p>
                </div>
              </el-upload>
            </div>
            <div class="flow-compact-actions">
              <el-button type="primary" :loading="docGrid.loading" :disabled="!canParseDocuments()" @click="parseDocuments">
                {{ parseStatus || "开始解析" }}
              </el-button>
            </div>
          </div>
        </section>
      </div>

      <section
        v-if="docStep === 0 && awaitingReviewAssist"
        class="ai-timeline ai-timeline-vertical audit-ai-timeline audit-prep-panel"
        aria-live="polite"
      >
        <header class="audit-prep-head">
          <h2 class="audit-page-title">AI 补全中</h2>
          <p class="audit-subtitle">补标题、属性和图片，完成后自动进入审核</p>
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

      <div v-if="docStep === 1 && reviewAiAllDone" class="step-panel audit-shell">
        <header class="audit-page-head">
          <button type="button" class="audit-back" @click="docStep = 0; docReached = 1">← 返回</button>
          <div class="audit-page-head-main">
            <div>
              <h2 class="audit-page-title">内容审核</h2>
              <p class="audit-subtitle">看标题、图、价/量就行。物流和店政策成稿时自动套。</p>
            </div>
          </div>
        </header>

        <section class="audit-guide">
          <div class="audit-guide-step">
            <span class="audit-guide-num">1</span>
            <div>
              <b>一键通过可成稿</b>
              <span>价、量、标题、关键词、有图 → 直接过</span>
            </div>
          </div>
          <div class="audit-guide-step">
            <span class="audit-guide-num">2</span>
            <div>
              <b>少数改一下</b>
              <span>点 ✎ 改标题/价/图，不用管物流属性</span>
            </div>
          </div>
          <div class="audit-guide-step">
            <span class="audit-guide-num">3</span>
            <div>
              <b>批量成稿</b>
              <span>已通过 {{ auditStats.approved }} 条，成稿后进草稿箱发布</span>
            </div>
          </div>
        </section>

        <section class="audit-toolbar-card">
          <div v-if="reviewStats.total" class="audit-summary-strip">
            <span>共 <b>{{ reviewStats.total }}</b></span>
            <span class="is-good">可成稿 <b>{{ reviewReadyStats.ready }}</b></span>
            <span class="is-good">已通过 <b>{{ auditStats.approved }}</b></span>
            <span v-if="reviewReadyStats.noPrice" class="is-warn">缺价量 {{ reviewReadyStats.noPrice }}</span>
            <span v-if="reviewReadyStats.noCopy" class="is-warn">缺文案 {{ reviewReadyStats.noCopy }}</span>
            <span v-if="reviewReadyStats.noImages" class="is-warn">缺图 {{ reviewReadyStats.noImages }}</span>
            <div class="audit-summary-actions">
              <el-button size="small" type="primary" @click="batchApproveReady">通过全部可成稿 ({{ reviewReadyStats.ready }})</el-button>
            </div>
          </div>
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
                {{ item.label }}<small> ({{ item.count }})</small>
              </button>
            </div>
            <div class="audit-toolbar-right">
              <el-input v-model="reviewSearch" clearable placeholder="搜名称 / SKU / 标题" class="audit-search" />
            </div>
          </div>
        </section>

        <section v-if="hasPendingImageJobs()" class="audit-ai-banner">
          后台并发生成图片：{{ docImageGenSummary || "进行中" }} — 可先审价/量/属性，图会自动刷新
        </section>

        <section class="audit-context-strip">
          <span>共 <b>{{ auditFieldColumns.length }}</b> 列</span>
          <span>表格填写 {{ auditColumnStats.user }}</span>
          <span>AI 补全 {{ auditColumnStats.ai }}</span>
          <span class="muted">表头含全部必填官方字段，后续 LLM 继承此表记忆继续补；左右滑看全部列</span>
        </section>

        <section class="audit-table-card">
          <div class="audit-table-scroll">
            <table class="audit-table audit-table-full">
              <thead>
                <tr>
                  <th class="col-check sticky-col"><el-checkbox v-model="docGrid.selectAll" @change="toggleSelectAll" /></th>
                  <th class="col-product sticky-col">商品</th>
                  <th
                    v-for="col in auditFieldColumns"
                    :key="col.id"
                    class="col-field"
                    :class="auditColumnClass(col)"
                  >
                    {{ col.label }}
                    <span v-if="col.required" class="need">必填</span>
                  </th>
                  <th class="col-images sticky-col-right">图</th>
                  <th class="col-status sticky-col-right">状态</th>
                  <th class="col-actions sticky-col-right">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="view in paginatedDocRowViews"
                  :key="view.row.line || view.index"
                  :class="{
                    'is-selected': view.row._selected,
                    'is-approved': rowAuditStatus(view.row) === 'approved',
                    'is-needs-fix': rowNeedsFix(view.row),
                  }"
                >
                  <td class="col-check sticky-col">
                    <el-checkbox v-model="view.row._selected" />
                  </td>
                  <td class="col-product sticky-col">
                    <div class="audit-product">
                      <div class="audit-product-thumb">
                        <img v-if="rowProductThumb(view.row)" :src="rowProductThumb(view.row)" alt="" />
                        <span v-else>{{ (view.row.name || view.row.sku || "?").slice(0, 1) }}</span>
                      </div>
                      <div class="audit-product-meta">
                        <b>{{ view.row.name || view.row.sku || "未命名" }}</b>
                        <span>{{ view.row.sku || `行 ${view.row.line}` }}</span>
                      </div>
                    </div>
                  </td>
                  <td
                    v-for="col in auditFieldColumns"
                    :key="`${view.index}-${col.id}`"
                    class="col-field"
                    :class="auditColumnClass(col)"
                    @dblclick="openRowDetail(view, col.id)"
                  >
                    <span class="audit-cell-text" :title="formatAuditCell(view.row, col)">{{ formatAuditCell(view.row, col) || "—" }}</span>
                  </td>
                  <td class="col-images sticky-col-right">
                    <div class="audit-image-strip">
                      <div
                        v-for="(url, imgIdx) in rowImageUrls(view.row).slice(0, 3)"
                        :key="`${view.index}-img-${imgIdx}`"
                        class="audit-image-thumb"
                      >
                        <img :src="url" alt="" />
                      </div>
                      <span v-if="rowImageCount(view.row) > 3" class="audit-image-more">+{{ rowImageCount(view.row) - 3 }}</span>
                      <span v-else-if="!rowImageCount(view.row)" class="audit-image-more is-warn">无</span>
                    </div>
                  </td>
                  <td class="col-status sticky-col-right">
                    <span class="audit-status" :class="`is-${rowStatusTone(view.row)}`">{{ rowStatusLabel(view.row) }}</span>
                  </td>
                  <td class="col-actions sticky-col-right">
                    <div class="audit-row-actions">
                      <button
                        v-if="rowAuditStatus(view.row) !== 'approved'"
                        type="button"
                        class="audit-action is-approve"
                        title="通过"
                        @click="approveRow(view.row)"
                      >✓</button>
                      <button type="button" class="audit-action is-view" title="编辑" @click="openRowDetail(view)">✎</button>
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

        <footer class="audit-footer">
          <div class="audit-footer-left">
            已选 <b>{{ docSelectedCount }}</b> · 已通过 <b>{{ auditStats.approved }}</b> / {{ reviewStats.total }}
          </div>
          <div class="audit-footer-right">
            <el-pagination
              v-model:current-page="reviewPage"
              v-model:page-size="reviewPageSize"
              :total="filteredDocRowViews.length"
              :page-sizes="[20, 50, 100, 200]"
              layout="total, prev, pager, next, sizes"
              size="small"
            />
            <el-button v-if="docSelectedCount" plain @click="batchApprove">通过已选</el-button>
            <el-button
              type="primary"
              size="large"
              :loading="docGrid.loading"
              :disabled="!auditStats.approved || !store.shopId || !doc.categoryId"
              @click="importDocRows"
            >
              批量成稿 ({{ auditStats.approved }})
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
            <ul v-if="rowDetailIssues.length" class="audit-drawer-issues">
              <li v-for="(issue, idx) in rowDetailIssues" :key="idx">{{ issue }}</li>
            </ul>
            <p v-else class="audit-drawer-ok">这条可以成稿，点下方保存或直接 ✓ 通过。</p>
            <div class="audit-drawer-section">
              <h4>改这里</h4>
              <div v-for="col in rowDetailColumns" :key="col.id" class="audit-drawer-field">
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
const LOCAL_DRAFT_PREFIX = "icbu-feed-draft";
const SMART_PLAN_CACHE_PREFIX = "icbu-smart-plan-cache";
const ECOSYSTEM_PREF_PREFIX = "icbu-feed-ecosystem";
const sessionId = ref("");
const deadSessionIds = loadDeadSessionIds();
const verifiedSessionIds = ref(new Set());
let sessionEnsurePromise = null;
let startPathPromise = null;
let persistInFlight = null;
let sessionGeneration = 0;
let persistBlockedUntil = 0;
let sessionCreatedAt = 0;
let sessionRecoveryInFlight = null;
let localDraftTimer = null;
let serverSyncTimer = null;
const sessionApiRetryDelaysFresh = [300, 700, 1200];
const sessionApiRetryDelaysBoot = [0, 80, 160];
const sessionBooting = ref(true);
const openSessions = ref([]);
const currentTitle = ref("");
const restoring = ref(false);
const docStep = ref(0);
const docReached = ref(0);
const docSteps = [
  { key: "setup", label: "准备表格" },
  { key: "grid", label: "审核成稿" },
];
const reviewFilter = ref("all");
const reviewSearch = ref("");
const reviewPage = ref(1);
const reviewPageSize = ref(50);
const rowDetailOpen = ref(false);
const rowDetailRow = ref(null);
const rowDetailFocusField = ref("");
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
const docImageFiles = ref([]);
const docSpreadsheetFiles = ref([]);
const folderInput = ref(null);
const photobankOpen = ref(false);
const photobankLoading = ref(false);
const photobankImages = ref([]);
const selectedPhotobankIds = ref(new Set());
const photobankDraftIds = ref(new Set());
const imageSetupMode = ref("pending"); // pending | confirmed | skipped
const visionPreview = ref([]);
let imageSyncTimer = null;
const IMAGE_SUFFIXES = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]);
const doc = reactive({
  categoryId: "",
  categoryName: "",
  batch: null,
  templateId: "",
  templateName: "",
  templateReason: "",
  reviewAiDone: false,
  llmColumnManifest: [],
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
const smartPlan = ref({ columns: [], column_count: 0, reasoning: "", tips: "", guarantee: "", category_name: "", habits: null });
const habitsShippingPick = ref("");
const habitsApplying = ref(false);
const useEcosystemAssistant = ref(false);
const smartPlanLoading = ref(false);
const smartPlanError = ref("");
const smartPlanShowAi = ref(false);
const smartPlanElapsedSec = ref(0);
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
let smartPlanAiDelayTimer = null;
let smartPlanElapsedTimer = null;
let smartPlanStepStartedAt = 0;

function createSmartPlanAiSteps() {
  return [
    { id: "vision", label: "识别商品图", status: "pending", detail: "" },
    { id: "schema", label: "读取官方字段", status: "pending", detail: "" },
    { id: "habits", label: "对照店铺模板", status: "pending", detail: "" },
    { id: "plan", label: "生成填写表列", status: "pending", detail: "" },
  ];
}

function resetSmartPlanAiSteps() {
  smartPlanAiSteps.value = createSmartPlanAiSteps();
}

function patchSmartPlanStep(id, patch) {
  smartPlanAiSteps.value = smartPlanAiSteps.value.map((step) => (step.id === id ? { ...step, ...patch } : step));
}

function startSmartPlanStepAnimation(hasVision = false) {
  stopSmartPlanStepTimers();
  resetSmartPlanAiSteps();
  smartPlanStepStartedAt = Date.now();
  smartPlanElapsedSec.value = 0;
  smartPlanElapsedTimer = window.setInterval(() => {
    if (!smartPlanLoading.value) return;
    smartPlanElapsedSec.value = Math.max(0, Math.floor((Date.now() - smartPlanStepStartedAt) / 1000));
  }, 1000);
  if (hasVision) {
    patchSmartPlanStep("vision", { status: "running", detail: "分析已确认的商品图…" });
  } else {
    patchSmartPlanStep("vision", { status: "done", detail: "未上传图片，按类目规则规划" });
    patchSmartPlanStep("schema", { status: "running", detail: "拉取类目 schema…" });
  }
  smartPlanStepTimer = window.setInterval(() => {
    if (!smartPlanLoading.value) return;
    const elapsed = Date.now() - smartPlanStepStartedAt;
    if (hasVision && elapsed >= 800) {
      patchSmartPlanStep("vision", { status: "done", detail: "读图完成" });
      patchSmartPlanStep("schema", { status: "running", detail: "拉取类目 schema…" });
    }
    if (elapsed >= (hasVision ? 2200 : 900)) {
      patchSmartPlanStep("schema", { status: "done", detail: "" });
      patchSmartPlanStep("habits", { status: "running", detail: "对照店铺默认与刊登模板…" });
    }
    if (elapsed >= (hasVision ? 3800 : 1800)) {
      patchSmartPlanStep("habits", { status: "done", detail: "" });
      const sec = Math.floor(elapsed / 1000);
      patchSmartPlanStep("plan", {
        status: "running",
        detail: sec >= 8 ? `AI 正在生成填写列…（${sec}s）` : "结合类目与图片生成填写列…",
      });
    }
  }, 400);
}

function stopSmartPlanStepTimers() {
  clearSmartPlanAiDelay();
  if (smartPlanStepTimer) {
    clearInterval(smartPlanStepTimer);
    smartPlanStepTimer = null;
  }
  if (smartPlanElapsedTimer) {
    clearInterval(smartPlanElapsedTimer);
    smartPlanElapsedTimer = null;
  }
}

function clearSmartPlanAiDelay() {
  if (smartPlanAiDelayTimer) {
    clearTimeout(smartPlanAiDelayTimer);
    smartPlanAiDelayTimer = null;
  }
}

function clearSmartPlanStepAnimation() {
  stopSmartPlanStepTimers();
  smartPlanStepStartedAt = 0;
  smartPlanElapsedSec.value = 0;
  smartPlanShowAi.value = false;
}

function finishSmartPlanStepAnimation() {
  stopSmartPlanStepTimers();
  const habitsDetail = habitsPanel.value?.selected_template_name
    ? `模板「${habitsPanel.value.selected_template_name}」${habitsReady.value ? "已就绪" : "待确认运费"}`
    : habitsPanel.value?.status === "needs_pick"
      ? "待选运费模板"
      : "";
  smartPlanAiSteps.value = smartPlanAiSteps.value.map((step) => ({
    ...step,
    status: step.status === "error" ? "error" : "done",
    detail:
      step.id === "plan"
        ? `完成（${smartPlan.value.column_count || 0} 列）`
        : step.id === "habits" && habitsDetail
          ? habitsDetail
          : step.detail,
  }));
  window.setTimeout(() => {
    if (!smartPlanLoading.value) {
      smartPlanShowAi.value = false;
    }
  }, 900);
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

const showReviewAiTimeline = computed(() => awaitingReviewAssist.value);

const awaitingReviewAssist = computed(() => {
  if (docStep.value !== 0 || !docGrid.rows.length) return false;
  if (docGrid.loading || reviewAssistRunning.value || hasPendingImageJobs()) return true;
  if (docReached.value >= 1 && !reviewAiAllDone.value) return true;
  return false;
});

const reviewAiAllDone = computed(() => {
  if (docGrid.loading || reviewAssistRunning.value) return false;
  return reviewAiSteps.value.every((step) => ["done", "skip"].includes(step.status));
});

function maybeEnterAuditStep() {
  if (!docGrid.rows.length || !reviewAiAllDone.value) return;
  if (docStep.value === 0 && docReached.value >= 1) {
    goToAuditStep();
  }
}

const coreFillIds = new Set(["sku", "price", "moq", "images", "brand", "name", "note"]);
const copyColumnIds = new Set(["title", "keywords", "highlights"]);
const tableCoreIds = new Set(["sku", "name", "price", "moq", "brand", "note", "title", "keywords", "highlights"]);
function selectedPhotobankList() {
  return photobankImages.value.filter((item) => selectedPhotobankIds.value.has(item.id || item.url));
}

function pendingPlanImageCountValue() {
  return allUploadImageFiles().length + selectedPhotobankList().length;
}

function hasPlanImages() {
  return imageSetupMode.value === "confirmed" && pendingPlanImageCountValue() > 0;
}

function hasUploadablePlanImages() {
  if (imageSetupMode.value !== "confirmed") return false;
  return allUploadImageFiles().some((item) => item.raw) || selectedPhotobankList().length > 0;
}

const pendingPlanImageCount = computed(() => pendingPlanImageCountValue());
const confirmedPlanImageCount = computed(() => (imageSetupMode.value === "confirmed" ? pendingPlanImageCountValue() : 0));
const canPickCategory = computed(() => imageSetupMode.value === "confirmed" || imageSetupMode.value === "skipped");

function invalidateImageSetupAfterChange() {
  if (imageSetupMode.value === "confirmed") {
    imageSetupMode.value = "pending";
    visionPreview.value = [];
    ElMessage.info("选图已变更，请重新点「确定选图」");
  }
}

function confirmPlanImages() {
  if (!pendingPlanImageCount.value) {
    ElMessage.warning("请先选择至少一张商品图，或点「暂不上传图片」");
    return;
  }
  imageSetupMode.value = "confirmed";
  photobankOpen.value = false;
  ElMessage.success(`已确认 ${pendingPlanImageCount.value} 张商品图，请选择类目`);
  scheduleLocalDraft();
  if (doc.categoryId) {
    void loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName, refresh: true });
  }
}

function skipPlanImages() {
  imageSetupMode.value = "skipped";
  photobankOpen.value = false;
  visionPreview.value = [];
  ElMessage.info("已跳过图片，将仅按类目生成填写表");
  scheduleLocalDraft();
  if (doc.categoryId) {
    void loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName, refresh: true });
  }
}

function resetImageSetup() {
  imageSetupMode.value = "pending";
  visionPreview.value = [];
  scheduleLocalDraft();
}

function canParseDocuments() {
  const sheets = docSpreadsheetFiles.value.filter((item) => item.raw && isSpreadsheetFile(item.name));
  return sheets.length > 0 || docSpreadsheetFiles.value.some((item) => item.raw);
}

function syncDocFilesFromParts() {
  docFiles.value = [...docImageFiles.value, ...docSpreadsheetFiles.value];
}

function onDocImageFilesChange() {
  syncDocFilesFromParts();
  invalidateImageSetupAfterChange();
  scheduleLocalDraft();
}

function onDocSpreadsheetChange() {
  syncDocFilesFromParts();
  scheduleLocalDraft();
}

async function openPhotobank() {
  photobankDraftIds.value = new Set(selectedPhotobankIds.value);
  photobankOpen.value = true;
  if (!photobankImages.value.length && store.shopId) {
    await loadPhotobank();
  }
}

async function loadPhotobank() {
  if (!store.shopId) return;
  photobankLoading.value = true;
  try {
    const data = await api.photobank(store.shopId, { page: 1, page_size: 48 });
    photobankImages.value = data.images || [];
  } catch (error) {
    ElMessage.error(error.message || "图片银行加载失败");
  } finally {
    photobankLoading.value = false;
  }
}

function togglePhotobankDraft(item) {
  const key = item.id || item.url;
  if (!key) return;
  const next = new Set(photobankDraftIds.value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  photobankDraftIds.value = next;
}

function cancelPhotobankPicker() {
  photobankOpen.value = false;
  photobankDraftIds.value = new Set(selectedPhotobankIds.value);
}

function confirmPhotobankPicker() {
  selectedPhotobankIds.value = new Set(photobankDraftIds.value);
  photobankOpen.value = false;
  invalidateImageSetupAfterChange();
  scheduleLocalDraft();
  if (selectedPhotobankIds.value.size) {
    ElMessage.success(`已从图片银行选 ${selectedPhotobankIds.value.size} 张，记得点「确定选图」`);
  }
}

function onDropImageFiles(event) {
  const files = Array.from(event.dataTransfer?.files || []).filter((file) => isImageFile(file.name));
  if (!files.length) {
    ElMessage.warning("请拖入图片文件");
    return;
  }
  const added = addDocImageFiles(files);
  if (added) ElMessage.success(`已添加 ${added} 张图片`);
}

function onDropDocFiles(event) {
  const files = Array.from(event.dataTransfer?.files || []);
  if (!files.length) return;
  const added = addDocSpreadsheetFiles(files);
  if (added) ElMessage.success(`已添加 ${added} 个文件`);
}

function addDocImageFiles(files) {
  const existing = new Set(docImageFiles.value.map((item) => fileStorageKey(item.raw || { name: item.name })));
  let added = 0;
  files.forEach((file) => {
    if (!file || !isImageFile(file.name)) return;
    const key = fileStorageKey(file);
    if (!key || existing.has(key)) return;
    docImageFiles.value.push({ name: file.webkitRelativePath || file.name, raw: file, status: "success" });
    existing.add(key);
    added += 1;
  });
  if (added) {
    syncDocFilesFromParts();
    invalidateImageSetupAfterChange();
    scheduleLocalDraft();
    scheduleDocImageSync();
  }
  return added;
}

function addDocSpreadsheetFiles(files) {
  const existing = new Set(docSpreadsheetFiles.value.map((item) => fileStorageKey(item.raw || { name: item.name })));
  let added = 0;
  files.forEach((file) => {
    if (!file) return;
    const key = fileStorageKey(file);
    if (!key || existing.has(key)) return;
    docSpreadsheetFiles.value.push({ name: file.name, raw: file, status: "success" });
    existing.add(key);
    added += 1;
  });
  if (added) {
    syncDocFilesFromParts();
    scheduleLocalDraft();
  }
  return added;
}

async function buildSmartPlanForm(categoryId, categoryName, refresh) {
  const body = new FormData();
  body.append("shop_id", store.shopId || "");
  body.append("category_id", categoryId);
  body.append("category_name", categoryName || "");
  if (refresh) body.append("refresh", "true");
  if (hasUploadablePlanImages()) {
    allUploadImageFiles().forEach((item) => {
      if (item.raw) body.append("files", item.raw, item.name);
    });
    const bank = selectedPhotobankList();
    if (bank.length) body.append("photobank_images", JSON.stringify(bank));
    return api.excelSmartPlanFromImages(body);
  }
  return api.excelSmartPlan({
    shop_id: store.shopId,
    category_id: categoryId,
    category_name: categoryName,
    ...(refresh ? { refresh: true } : {}),
  });
}

async function fetchSmartPlanFallback(categoryId, categoryName) {
  return api.excelSmartPlan({
    shop_id: store.shopId,
    category_id: categoryId,
    category_name: categoryName,
    refresh: false,
  });
}
const planImageCount = computed(() => confirmedPlanImageCount.value);
const smartPlanAiFillCount = computed(() => {
  const n = smartPlan.value.ai_fill_attr_count || 0;
  if (n) return n;
  return (smartPlan.value.ai_fills || []).filter((item) => String(item.group || "") === "schema").length;
});
const smartPlanEvidenceCount = computed(() => {
  const ids = smartPlan.value.evidence_column_ids || [];
  if (ids.length) return ids.length;
  return (smartPlan.value.columns || []).filter((col) => String(col.id || "").startsWith("attr.")).length;
});
const smartColumnLabels = computed(() =>
  (smartPlan.value.columns || []).map((col) => col.label || col.header || col.id).filter(Boolean),
);
const canDownloadTemplate = computed(
  () => Boolean(doc.categoryId && smartPlan.value.columns?.length && !smartPlanLoading.value),
);
const showSmartPlanTimeline = computed(() => smartPlanLoading.value || smartPlanShowAi.value);
const smartPlanLoadingText = computed(() => {
  const running = smartPlanAiSteps.value.find((step) => step.status === "running");
  if (running?.detail) return running.detail;
  if (running?.label) return `正在${running.label}…`;
  const sec = smartPlanElapsedSec.value;
  return sec >= 8 ? `正在生成填写表…（${sec}s）` : "正在生成填写表…";
});
const planSourceLabel = computed(() => {
  const planner = String(smartPlan.value.planner || "");
  if (planner.includes("vision")) return "含读图";
  if (planner.includes("llm")) return "AI 规划";
  if (planner) return "规则规划";
  return "";
});
const habitsPanel = computed(() => smartPlan.value.habits || null);
const habitsReady = computed(() => Boolean(habitsPanel.value?.ready));
const habitsNeedsPick = computed(
  () => habitsPanel.value?.status === "needs_pick" && (habitsPanel.value?.shipping_options?.length || 0) > 0,
);
const habitsSummaryLine = computed(() => {
  const habits = habitsPanel.value;
  if (!habits) return "";
  const parts = [];
  const shipping = (habits.checks || []).find((item) => item.id === "shippingTemplateId");
  if (shipping?.value) parts.push(`运费 ${shipping.value}`);
  if (habits.selected_template_name) parts.push(`模板 ${habits.selected_template_name}`);
  if (doc.templateName && doc.templateName !== habits.selected_template_name) {
    parts.push(`审核模板 ${doc.templateName}`);
  }
  return parts.join(" · ");
});
const excelImageMode = computed(() => `${excel.photoPolicy || "complete"}_${excel.emptyPolicy || "draw"}`);
const docPercent = computed(() => {
  if (!doc.batch?.count) return 0;
  return Math.min(100, Math.round((docProgress.value.done / doc.batch.count) * 100));
});
const docDataColumns = computed(() => docGrid.columns.filter((col) => col.id !== "images"));
const auditFieldColumns = computed(() => docDataColumns.value);
const auditTableColSpan = computed(() => 2 + auditFieldColumns.value.length + 3);
const auditColumnStats = computed(() => {
  let user = 0;
  let ai = 0;
  auditFieldColumns.value.forEach((col) => {
    const src = String(col.source || "");
    if (src === "user" || col.required || tableCoreIds.has(col.id)) user += 1;
    else ai += 1;
  });
  return { user, ai };
});
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
const reviewReadyStats = computed(() => {
  const rows = docGrid.rows || [];
  let ready = 0;
  let noCopy = 0;
  let noImages = 0;
  let noPrice = 0;
  rows.forEach((row) => {
    if (!rowReady(row)) noPrice += 1;
    if (rowMissingCopy(row)) noCopy += 1;
    if (rowImageCount(row) < 1) noImages += 1;
    if (rowAuditReady(row)) ready += 1;
  });
  return { ready, noCopy, noImages, noPrice };
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
const auditFilterOptions = computed(() => {
  const rows = docGrid.rows || [];
  let needsFix = 0;
  rows.forEach((row) => {
    if (rowNeedsFix(row)) needsFix += 1;
  });
  return [
    { id: "all", label: "全部", count: auditStats.value.total },
    { id: "ready", label: "可成稿", count: reviewReadyStats.value.ready },
    { id: "needs_fix", label: "需改", count: needsFix },
    { id: "approved", label: "已通过", count: auditStats.value.approved },
  ];
});
const rowDetailTitle = computed(() => {
  if (!rowDetailRow.value) return "商品详情";
  return rowDetailRow.value.name || rowDetailRow.value.sku || "商品详情";
});
const rowDetailColumns = computed(() => {
  const cols = [];
  const seen = new Set();
  const push = (col) => {
    if (col && !seen.has(col.id)) {
      cols.push(col);
      seen.add(col.id);
    }
  };
  ["sku", "name", "brand", "price", "moq", "note"].forEach((id) => push(docDataColumns.value.find((item) => item.id === id)));
  ["title", "keywords", "highlights"].forEach((id) => push(docDataColumns.value.find((item) => item.id === id)));
  docRequiredAttrColumns.value.forEach((col) => push(col));
  docScoreAttrColumns.value.forEach((col) => push(col));
  docDataColumns.value.forEach((col) => push(col));
  return cols;
});
const rowDetailIssues = computed(() => {
  const row = rowDetailRow.value;
  if (!row) return [];
  const items = [];
  if (!rowReady(row)) items.push("填价格和起订量（AI 不会代填）");
  if (rowMissingCopy(row)) items.push("补标题或关键词");
  if (rowImageCount(row) < 1) items.push("至少配一张图");
  if (issueLineSet.value.has(row.line)) items.push("价/量格式有问题");
  rowEmptyRequiredAttrs(row).forEach((col) => items.push(`必填「${col.label}」还空着`));
  return items;
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
        case "ready":
          return rowAuditReady(row);
        case "needs_fix":
          return rowNeedsFix(row);
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
      uploadImageNames: docImageFiles.value.map((item) => item.name).filter(Boolean),
      uploadSpreadsheetNames: docSpreadsheetFiles.value.map((item) => item.name).filter(Boolean),
      photobankIds: [...selectedPhotobankIds.value],
      imageSetupMode: imageSetupMode.value,
      visionPreview: visionPreview.value,
      useEcosystemAssistant: useEcosystemAssistant.value,
      reviewAiDone: doc.reviewAiDone || reviewAiAllDone.value,
      llmColumnManifest: doc.llmColumnManifest,
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

function localDraftStorageKey() {
  const uid = store.user?.id || "guest";
  const sid = store.shopId || "";
  return `${LOCAL_DRAFT_PREFIX}:${uid}:${sid}`;
}

function ecosystemPrefKey() {
  return `${ECOSYSTEM_PREF_PREFIX}:${store.user?.id || "guest"}`;
}

function loadEcosystemPref() {
  try {
    return localStorage.getItem(ecosystemPrefKey()) === "1";
  } catch {
    return false;
  }
}

function saveEcosystemPref(value) {
  try {
    localStorage.setItem(ecosystemPrefKey(), value ? "1" : "0");
  } catch {
    /* ignore */
  }
}

function onEcosystemToggleChange(value) {
  saveEcosystemPref(value);
  void persistSession();
}

const SMART_PLAN_CORE_IDS = new Set(["sku", "price", "moq", "images", "brand", "name", "note"]);

function isCoreOnlySmartPlan(plan) {
  const ids = (plan?.columns || []).map((col) => col.id).filter(Boolean);
  if (!ids.length) return true;
  return ids.every((id) => SMART_PLAN_CORE_IDS.has(id));
}

function smartPlanCacheKey(categoryId) {
  return `${SMART_PLAN_CACHE_PREFIX}:${store.user?.id || "guest"}:${store.shopId || ""}:${categoryId}`;
}

function loadLocalSmartPlan(categoryId) {
  if (!categoryId) return null;
  try {
    const raw = localStorage.getItem(smartPlanCacheKey(categoryId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveLocalSmartPlan(categoryId, plan) {
  if (!categoryId || !plan?.columns?.length || isCoreOnlySmartPlan(plan)) return;
  try {
    localStorage.setItem(
      smartPlanCacheKey(categoryId),
      JSON.stringify({
        ...plan,
        category_id: categoryId,
        cached_at: Date.now(),
      }),
    );
  } catch {
    /* ignore quota errors */
  }
}

function hasSmartPlanForCategory(categoryId) {
  return Boolean(
    categoryId
    && smartPlan.value.columns?.length
    && String(smartPlan.value.category_id || doc.categoryId) === String(categoryId),
  );
}

function applySmartPlan(raw, categoryId = "") {
  const plan = normalizeSmartPlan({ ...raw, category_id: raw?.category_id || categoryId });
  smartPlan.value = plan;
  if (!docGrid.rows.length) {
    docGrid.columns = plan.columns || [];
  }
  syncHabitsFromPlan(plan);
  if (raw?.vision_samples?.length) {
    visionPreview.value = raw.vision_samples;
  }
  if (categoryId) saveLocalSmartPlan(categoryId, plan);
  return plan;
}

function loadLocalDraft() {
  try {
    const raw = localStorage.getItem(localDraftStorageKey());
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveLocalDraft() {
  if (sessionBooting.value || restoring.value) return;
  try {
    localStorage.setItem(
      localDraftStorageKey(),
      JSON.stringify({
        sessionId: sessionId.value,
        step: docStep.value,
        reached: docReached.value,
        payload: sessionPayload(),
        updatedAt: Date.now(),
      }),
    );
  } catch {
    /* quota */
  }
}

function clearLocalDraft() {
  try {
    localStorage.removeItem(localDraftStorageKey());
  } catch {
    /* ignore */
  }
}

function scheduleLocalDraft() {
  clearTimeout(localDraftTimer);
  localDraftTimer = setTimeout(saveLocalDraft, 250);
}

function applyDraftPayload(draft) {
  const payload = draft?.payload || {};
  if (payload.doc) {
    doc.categoryId = payload.doc.categoryId || doc.categoryId;
    doc.categoryName = payload.doc.categoryName || doc.categoryName;
    doc.batch = payload.doc.batch ?? doc.batch;
    doc.templateId = payload.doc.templateId || doc.templateId;
    doc.templateName = payload.doc.templateName || doc.templateName;
    doc.templateReason = payload.doc.templateReason || doc.templateReason;
    docGrid.columns = payload.doc.columns?.length ? payload.doc.columns : docGrid.columns;
    docGrid.rows = payload.doc.rows?.length ? normalizeDocRows(payload.doc.rows) : docGrid.rows;
    docGrid.row_issues = payload.doc.row_issues || docGrid.row_issues;
    docGrid.warnings = payload.doc.warnings || docGrid.warnings;
    docGrid.row_count = payload.doc.row_count || docGrid.rows.length;
    docGrid.ready_count = payload.doc.ready_count || docGrid.ready_count;
    docGrid.source = payload.doc.source || docGrid.source;
    if (payload.doc.smartPlan?.columns?.length) {
      smartPlan.value = normalizeSmartPlan(payload.doc.smartPlan);
    }
    applyExcelImageMode(payload.doc.imageMode, payload.doc.photoPolicy, payload.doc.emptyPolicy);
    if (typeof payload.doc.useEcosystemAssistant === "boolean") {
      useEcosystemAssistant.value = payload.doc.useEcosystemAssistant;
    }
    if (payload.doc.reviewAiDone) {
      doc.reviewAiDone = true;
      markReviewAiDone();
    }
    if (payload.doc.llmColumnManifest?.length) {
      doc.llmColumnManifest = payload.doc.llmColumnManifest;
    }
    restoreUploadNameLists(payload.doc);
  }
  if (typeof draft?.step === "number") {
    let step = Math.min(draft.step, docSteps.length - 1);
    const rowCount = payload.doc?.rows?.length || payload.doc?.row_count || docGrid.rows.length;
    if (step === 0 && rowCount > 0 && (draft.reached >= 1 || payload.doc?.source)) {
      step = 1;
    }
    docStep.value = step;
  }
  if (typeof draft?.reached === "number") {
    docReached.value = Math.min(Math.max(draft.reached, docStep.value), docSteps.length - 1);
  }
}

function mergeLocalDraftIfNewer() {
  const draft = loadLocalDraft();
  if (!draft?.payload) return;
  if (draft.sessionId && sessionId.value && draft.sessionId !== sessionId.value) return;
  applyDraftPayload(draft);
}

function shouldSyncToServer() {
  if (sessionBooting.value || restoring.value || docGrid.loading || reviewAssistRunning.value) return false;
  if (Date.now() < persistBlockedUntil) return false;
  if (sessionRecoveryInFlight) return false;
  if (!sessionId.value || deadSessionIds.has(sessionId.value)) return false;
  if (!isKnownOpenSession(sessionId.value) && !sessionFromOpenList(sessionId.value)) return false;
  return true;
}

function scheduleServerSync() {
  if (!shouldSyncToServer()) return;
  clearTimeout(serverSyncTimer);
  serverSyncTimer = setTimeout(() => {
    void persistSessionToServer();
  }, 4000);
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

function isSessionFresh() {
  return sessionCreatedAt > 0 && Date.now() - sessionCreatedAt < 10000;
}

function retryDelaysForSessionWrite() {
  return isSessionFresh() ? sessionApiRetryDelaysFresh : [];
}

async function ensureSessionRecord(id) {
  if (!id || deadSessionIds.has(id)) return null;
  if (sessionId.value !== id && loadLocalDraft()?.sessionId !== id) return null;
  try {
    const draft = loadLocalDraft();
    const saved = await api.saveFeedSession(id, {
      shop_id: store.shopId || "",
      step: draft?.sessionId === id && typeof draft.step === "number" ? draft.step : currentStep(),
      reached: draft?.sessionId === id && typeof draft.reached === "number" ? draft.reached : currentReached(),
      payload: draft?.sessionId === id && draft.payload ? draft.payload : sessionPayload(),
    });
    verifySession(id);
    rememberOpenSession(id);
    return saved;
  } catch (error) {
    if (isSessionApiMissing(error)) return null;
    throw error;
  }
}

async function upsertSessionFromLocal(id) {
  if (!id || deadSessionIds.has(id)) return null;
  const pushed = await pushLocalSessionToServer(id);
  if (pushed) return pushed;
  return ensureSessionRecord(id);
}

function rememberRemoteSession(remote) {
  if (!remote?.id) return remote;
  verifySession(remote.id);
  openSessions.value = [remote, ...openSessions.value.filter((item) => item.id !== remote.id)];
  return remote;
}

async function fetchFeedSessionOnce(id) {
  return api.getFeedSession(id);
}

async function fetchFeedSessionWithRetry(id, options = {}) {
  const { boot = false } = options;
  let lastError = null;
  const delays = boot ? sessionApiRetryDelaysBoot : [];
  for (let attempt = 0; attempt <= delays.length; attempt += 1) {
    try {
      return await api.getFeedSession(id);
    } catch (error) {
      lastError = error;
      if (isSessionApiMissing(error)) throw error;
      if (attempt >= delays.length) throw error;
      await sleep(delays[attempt]);
    }
  }
  throw lastError || new Error("加载失败");
}

async function pushLocalSessionToServer(id) {
  if (sessionId.value !== id && loadLocalDraft()?.sessionId !== id) return null;
  const draft = loadLocalDraft();
  const payload = draft?.sessionId === id && draft.payload ? draft.payload : sessionPayload();
  const step = draft?.sessionId === id && typeof draft.step === "number" ? draft.step : currentStep();
  const reached = draft?.sessionId === id && typeof draft.reached === "number" ? draft.reached : currentReached();
  try {
    const saved = await saveSessionWithRetry(id, {
      shop_id: store.shopId || "",
      step,
      reached,
      payload,
    });
    verifySession(id);
    rememberOpenSession(id);
    return saved;
  } catch {
    return null;
  }
}

async function saveSessionWithRetry(id, body) {
  let lastError = null;
  const delays = retryDelaysForSessionWrite();
  for (let attempt = 0; attempt <= delays.length; attempt += 1) {
    try {
      return await api.saveFeedSession(id, body);
    } catch (error) {
      lastError = error;
      // PATCH upserts — 404 should not repeat; only retry fresh creates on blob lag
      if (isSessionApiMissing(error)) throw error;
      if (attempt >= delays.length) throw error;
      await sleep(delays[attempt]);
    }
  }
  throw lastError || new Error("保存失败");
}

async function uploadSessionFilesWithRetry(id, form) {
  let lastError = null;
  const delays = retryDelaysForSessionWrite();
  for (let attempt = 0; attempt <= delays.length; attempt += 1) {
    try {
      return await api.uploadFeedSessionFiles(id, form);
    } catch (error) {
      lastError = error;
      if (!isSessionApiMissing(error) || attempt >= delays.length) throw error;
      await sleep(delays[attempt]);
    }
  }
  throw lastError || new Error("上传失败");
}

async function markSessionDeadAndRecover(deadId, options = {}) {
  const { quiet = true } = options;
  if (deadId && sessionRecoveryInFlight) {
    return sessionRecoveryInFlight;
  }
  sessionRecoveryInFlight = (async () => {
    if (deadId) forgetSession(deadId);
    if (sessionId.value === deadId) {
      sessionId.value = "";
    }
    if (route.query.session === deadId) router.replace({ query: {} });
    clearTimeout(saveTimer);
    clearTimeout(imageSyncTimer);
    persistBlockedUntil = Date.now() + 2000;
    await migrateOrphanSession({ quiet });
    if (!quiet) ElMessage.warning("这条做到一半的记录已失效，已为你新建批量任务");
  })().finally(() => {
    sessionRecoveryInFlight = null;
  });
  return sessionRecoveryInFlight;
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

function touchSessionCreatedAt() {
  sessionCreatedAt = Date.now();
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
  const remote = await resolveSessionById(sessionId.value);
  if (remote) {
    return true;
  }
  const staleId = sessionId.value;
  await markSessionDeadAndRecover(staleId, { quiet });
  return Boolean(sessionId.value);
}

async function persistSession(options = {}) {
  const { server = false } = options;
  saveLocalDraft();
  if (server) {
    if (persistInFlight) return persistInFlight;
    persistInFlight = persistSessionToServer().finally(() => {
      persistInFlight = null;
    });
    return persistInFlight;
  }
  scheduleServerSync();
}

async function persistSessionToServer() {
  if (!shouldSyncToServer()) return;
  const generation = sessionGeneration;
  const targetId = sessionId.value;
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
  touchSessionCreatedAt();
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
    if (typeof payload.doc.useEcosystemAssistant === "boolean") {
      useEcosystemAssistant.value = payload.doc.useEcosystemAssistant;
    }
    if (payload.doc.reviewAiDone) {
      doc.reviewAiDone = true;
      markReviewAiDone();
    }
    if (payload.doc.llmColumnManifest?.length) {
      doc.llmColumnManifest = payload.doc.llmColumnManifest;
    }
    restoreUploadNameLists(payload.doc);
  } else {
    doc.categoryId = "";
    doc.categoryName = "";
    doc.batch = null;
    doc.templateId = "";
    doc.templateName = "";
    doc.templateReason = "";
    doc.reviewAiDone = false;
    doc.llmColumnManifest = [];
    docGrid.columns = [];
    docGrid.rows = [];
    docGrid.row_issues = [];
    docGrid.warnings = [];
    docGrid.row_count = 0;
    docGrid.ready_count = 0;
    docGrid.source = "";
    docFiles.value = [];
    docImageFiles.value = [];
    docSpreadsheetFiles.value = [];
    selectedPhotobankIds.value = new Set();
    photobankDraftIds.value = new Set();
    imageSetupMode.value = "pending";
    visionPreview.value = [];
  }
  if (session.path === "excel" || session.path === "full") {
    migrateLegacyExcelSession(session, payload);
  } else {
    docStep.value = Math.min(session.step || 0, docSteps.length - 1);
    if (docStep.value > 1) docStep.value = 1;
    docReached.value = Math.min(session.reached ?? 0, docSteps.length - 1);
    if (docStep.value === 1 && docGrid.rows.length && !doc.reviewAiDone) {
      doc.reviewAiDone = true;
      markReviewAiDone();
    }
  }
  restoring.value = false;
  mergeLocalDraftIfNewer();
  if (docGrid.rows.length > 0 && (docReached.value >= 1 || docGrid.source)) {
    docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
    if (reviewAiAllDone.value) {
      goToAuditStep();
    } else if (docStep.value === 0) {
      void runReviewAssist(true);
    }
  }
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
    smartPlan.value = { columns: [], column_count: 0, reasoning: "", tips: "", guarantee: "", category_name: "" };
    applySession(created);
    touchSessionCreatedAt();
    verifySession(created.id);
    clearLocalDraft();
    saveLocalDraft();
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
  if (docGrid.rows.length > 0 && (docReached.value >= 1 || docGrid.source)) {
    docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
    if (reviewAiAllDone.value) {
      goToAuditStep();
    } else if (docStep.value === 0) {
      void runReviewAssist(true);
    }
  }
  if (!doc.categoryId || !store.shopId) return;
  if (hasSmartPlanForCategory(doc.categoryId)) {
    ensureGridPolling();
    if (!doc.reviewAiDone && docStep.value === 1 && (rowsNeedingCopy().length || rowsNeedingImageJobs().length)) {
      void runReviewAssist(true);
    }
    return;
  }
  const localCached = hasUploadablePlanImages() ? null : loadLocalSmartPlan(doc.categoryId);
  if (localCached?.columns?.length && !isCoreOnlySmartPlan(localCached)) {
    applySmartPlan({ ...localCached, cached: true }, doc.categoryId);
  }
  void loadSmartPlan({
    categoryId: doc.categoryId,
    categoryName: doc.categoryName,
    background: Boolean(localCached?.columns?.length && !isCoreOnlySmartPlan(localCached)),
    refresh: Boolean(isCoreOnlySmartPlan(localCached)),
  }).catch((error) => {
    if (!localCached?.columns?.length || isCoreOnlySmartPlan(localCached)) ElMessage.error(error.message);
  });
  ensureGridPolling();
  if (!doc.reviewAiDone && docStep.value === 1 && (rowsNeedingCopy().length || rowsNeedingImageJobs().length)) {
    void runReviewAssist(true);
  }
}

async function resolveSessionById(id, options = {}) {
  const { boot = false } = options;
  if (!id || deadSessionIds.has(id)) return null;
  const cached = sessionFromOpenList(id);
  if (cached) {
    verifySession(id);
    return cached;
  }
  const upserted = await upsertSessionFromLocal(id);
  if (upserted) return rememberRemoteSession(upserted);
  try {
    const remote = boot
      ? await fetchFeedSessionWithRetry(id, { boot: true })
      : await fetchFeedSessionOnce(id);
    return rememberRemoteSession(remote);
  } catch (error) {
    if (!isSessionApiMissing(error)) throw error;
    forgetSession(id);
  }
  return null;
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
  const session = await resolveSessionById(id);
  if (!session) {
    if (route.query.session === id) router.replace({ query: {} });
    const fallback = openSessions.value.find((item) => !deadSessionIds.has(item.id));
    if (fallback && fallback.id !== id) {
      await resumeSession(fallback.id, { ...options, skipListReload: true });
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
  await persistSession({ server: true });
  await startPath();
}

async function hydrateSessionFromServer(id) {
  if (!id || deadSessionIds.has(id)) return;
  try {
    void loadOpenSessions();
    const remote = await resolveSessionById(id, { boot: true });
    if (remote) {
      applySession(remote);
      void finishResumeSession();
      return;
    }
    if (sessionId.value === id) {
      forgetSession(id);
      if (route.query.session === id) router.replace({ query: {} });
    }
  } catch {
    /* keep local draft visible */
  }
}

async function bootSession() {
  sessionBooting.value = true;
  try {
    const wanted = route.query.session ? String(route.query.session) : "";
    const localDraft = !wanted ? loadLocalDraft() : null;
    if (localDraft?.sessionId && !deadSessionIds.has(localDraft.sessionId)) {
      sessionId.value = localDraft.sessionId;
      applyDraftPayload(localDraft);
      verifySession(localDraft.sessionId);
      router.replace({ query: { session: localDraft.sessionId } });
      sessionBooting.value = false;
      void hydrateSessionFromServer(localDraft.sessionId);
      return;
    }

    const shopsReady = store.shops.length ? Promise.resolve() : store.ensureShops();

    if (wanted && deadSessionIds.has(wanted)) {
      router.replace({ query: {} });
    } else if (wanted && !deadSessionIds.has(wanted)) {
      sessionId.value = wanted;
      const draft = loadLocalDraft();
      if (draft?.sessionId === wanted) {
        applyDraftPayload(draft);
        verifySession(wanted);
        router.replace({ query: { session: wanted } });
        sessionBooting.value = false;
        void hydrateSessionFromServer(wanted);
        return;
      }
      const [, remote] = await Promise.all([
        shopsReady,
        resolveSessionById(wanted, { boot: true }),
      ]);
      void loadOpenSessions();
      if (remote) {
        applySession(remote);
        verifySession(wanted);
        router.replace({ query: { session: wanted } });
        void finishResumeSession();
        return;
      }
      forgetSession(wanted);
      router.replace({ query: {} });
    }

    await Promise.all([shopsReady, loadOpenSessions()]);
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
  void api.health().then((health) => {
    aiServiceReady.value = health.ai_enabled !== false;
  }).catch(() => {
    aiServiceReady.value = null;
  });
  const shopsReady = store.shops.length ? Promise.resolve() : store.ensureShops();
  void shopsReady.then(() => {
    if (store.shopId) void prefetchCategoryPicker(store.shopId);
  });
  await Promise.all([bootSession(), shopsReady]);
});

let saveTimer = null;
watch(
  () => docStep.value,
  (step) => {
    if (step === 1 && docGrid.rows.length) {
      docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
      void autoStartReviewImages();
      ensureGridPolling();
    }
  },
);

watch(
  () => [excel.photoPolicy, excel.emptyPolicy, docStep.value, doc.categoryId, docGrid.row_count],
  () => {
    if (sessionBooting.value || restoring.value) return;
    scheduleLocalDraft();
    if (docStep.value >= 0) scheduleServerSync();
  },
);
watch(
  () => store.shopId,
  (shopId) => {
    if (shopId) void prefetchCategoryPicker(shopId);
  },
);
watch(
  () => docGrid.rows,
  () => {
    if (sessionBooting.value || restoring.value || docGrid.loading || reviewAssistRunning.value) return;
    scheduleLocalDraft();
  },
  { deep: true },
);
watch(
  () => reviewAiAllDone.value,
  (done) => {
    if (!done || !docGrid.rows.length) return;
    maybeEnterAuditStep();
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
  [...docImageFiles.value, ...excelImages.value].forEach((item) => {
    if (!item?.raw || !isImageFile(item.name)) return;
    const key = fileStorageKey(item.raw);
    if (seen.has(key)) return;
    seen.add(key);
    items.push(item);
  });
  return items;
}

function restoreUploadNameLists(payload = {}) {
  const imageNames = payload.uploadImageNames?.length
    ? payload.uploadImageNames
    : (payload.uploadNames || []).filter((name) => isImageFile(name));
  const sheetNames = payload.uploadSpreadsheetNames?.length
    ? payload.uploadSpreadsheetNames
    : (payload.uploadNames || []).filter((name) => isSpreadsheetFile(name));
  docImageFiles.value = imageNames.map((name) => ({ name, status: "success" }));
  docSpreadsheetFiles.value = sheetNames.map((name) => ({ name, status: "success" }));
  syncDocFilesFromParts();
  if (payload.photobankIds?.length) {
    selectedPhotobankIds.value = new Set(payload.photobankIds);
    photobankDraftIds.value = new Set(payload.photobankIds);
  }
  if (payload.imageSetupMode === "confirmed" || payload.imageSetupMode === "skipped") {
    imageSetupMode.value = payload.imageSetupMode;
  } else if (payload.uploadImageNames?.length || payload.photobankIds?.length) {
    imageSetupMode.value = "pending";
  } else {
    imageSetupMode.value = "pending";
  }
  if (payload.visionPreview?.length) {
    visionPreview.value = payload.visionPreview;
  }
}

function addDocFiles(files) {
  const images = files.filter((file) => file && isImageFile(file.name));
  const sheets = files.filter((file) => file && !isImageFile(file.name));
  const added = addDocImageFiles(images) + addDocSpreadsheetFiles(sheets);
  if (added) {
    docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
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
  const added = addDocImageFiles(picked);
  event.target.value = "";
  if (added) ElMessage.success(`已添加 ${added} 张图片`);
}

function onDocFilesChange() {
  scheduleLocalDraft();
}

function scheduleDocImageSync() {
  if (!sessionId.value || sessionBooting.value || deadSessionIds.has(sessionId.value)) return;
  clearTimeout(imageSyncTimer);
  imageSyncTimer = setTimeout(() => {
    void syncDocImagesToSession();
  }, 1200);
}

async function syncDocImagesToSession() {
  if (!sessionId.value || deadSessionIds.has(sessionId.value)) return;
  const files = allUploadImageFiles().filter((item) => item.raw);
  if (!files.length) return;
  const form = new FormData();
  form.append("kind", "excel_images");
  form.append("keep", files.map((item) => item.name).join(","));
  files.forEach((item) => form.append("files", item.raw, item.name));
  try {
    await uploadSessionFilesWithRetry(sessionId.value, form);
  } catch {
    /* best effort — import still tries session fallback */
  }
}

async function loadSmartPlan(override = null) {
  const categoryId = override?.categoryId ?? doc.categoryId ?? "";
  const categoryName = override?.categoryName ?? doc.categoryName ?? "";
  const refresh = Boolean(override?.refresh);
  const background = Boolean(override?.background);
  const hasVision = hasUploadablePlanImages();
  if (!store.shopId || !categoryId) return;

  if (!background) {
    smartPlanLoading.value = true;
    smartPlanError.value = "";
    smartPlanShowAi.value = true;
    startSmartPlanStepAnimation(hasVision);
  }

  const finishPlanUi = (raw) => {
    if (background) return;
    smartPlanError.value = "";
    finishSmartPlanStepAnimation();
  };

  try {
    const raw = await buildSmartPlanForm(categoryId, categoryName, refresh);
    applySmartPlan(raw, categoryId);
    finishPlanUi(raw);
    void maybeAutoAdoptHabits(smartPlan.value);
  } catch (error) {
    const msg = String(error.message || "");
    if (msg.includes("店铺不存在")) {
      await store.ensureShops();
      if (store.shopId) {
        const raw = await buildSmartPlanForm(categoryId, categoryName, refresh);
        applySmartPlan(raw, categoryId);
        finishPlanUi(raw);
        void maybeAutoAdoptHabits(smartPlan.value);
        return;
      }
    }
    if (hasVision && !override?.fallbackTried) {
      try {
        const raw = await fetchSmartPlanFallback(categoryId, categoryName);
        applySmartPlan(raw, categoryId);
        finishPlanUi(raw);
        void maybeAutoAdoptHabits(smartPlan.value);
        ElMessage.warning("读图规划失败，已改用类目规则表，仍可下载填写");
        return;
      } catch {
        /* try error surface below */
      }
    }
    if (!background) {
      stopSmartPlanStepTimers();
      smartPlanShowAi.value = true;
      smartPlanError.value = msg || "生成填写表失败，请重试";
      patchSmartPlanStep("plan", { status: "error", detail: smartPlanError.value });
    }
    throw error;
  } finally {
    if (!background) {
      smartPlanLoading.value = false;
    }
  }
}

function normalizeSmartPlan(raw) {
  const columns = (raw.columns || []).map((col) => ({
    id: col.id,
    header: col.header || col.label || col.id,
    label: col.label || col.header || col.id,
    required: Boolean(col.required),
    options: col.options || [],
    hint: col.hint || "",
    kind: col.kind,
    group: col.group,
    field_id: col.field_id,
    source: col.source,
  }));
  return {
    category_id: raw.category_id || "",
    category_name: raw.category_name || "",
    column_count: raw.column_count || columns.length,
    columns,
    reasoning: raw.reasoning || "",
    tips: raw.tips || "",
    guarantee: raw.guarantee || raw.user_fill_contract || "",
    cached: Boolean(raw.cached),
    planner: raw.planner || "",
    covered_by_shop: raw.covered_by_shop || [],
    covered_by_template: raw.covered_by_template || [],
    ai_fills: raw.ai_fills || [],
    ai_fill_attr_count: raw.ai_fill_attr_count || (raw.ai_fill_attrs || []).length || 0,
    evidence_column_ids: raw.evidence_column_ids || [],
    review_note: raw.review_note || "",
    habits: raw.habits || null,
    selected_template_id: raw.selected_template_id || raw.habits?.selected_template_id || "",
    selected_template_name: raw.selected_template_name || raw.habits?.selected_template_name || "",
  };
}

function syncHabitsFromPlan(plan) {
  const habits = plan?.habits;
  if (!habits) return;
  const rec = habits.recommended_shipping_template_id || habits.shipping_recommendation?.shipping_template_id || "";
  habitsShippingPick.value = rec || habitsShippingPick.value;
  const tid = plan.selected_template_id || habits.selected_template_id || "";
  if (tid) {
    doc.templateId = tid;
    doc.templateName = plan.selected_template_name || habits.selected_template_name || doc.templateName;
    doc.templateReason = habits.selected_template_is_auto ? "已自动创建类目模板" : "规划阶段已匹配";
  }
}

let habitsAutoAdoptKey = "";

function habitsAutoAdoptEligible(plan) {
  const habits = plan?.habits;
  if (!habits || habits.ready || habitsApplying.value) return false;
  if (habits.status !== "needs_pick") return false;
  const rec = habits.shipping_recommendation;
  if (!rec || rec.confidence !== "high") return false;
  const shippingId = habits.recommended_shipping_template_id || rec.shipping_template_id;
  if (!shippingId) return false;
  const key = `${doc.categoryId}:${shippingId}`;
  if (habitsAutoAdoptKey === key) return false;
  habitsAutoAdoptKey = key;
  habitsShippingPick.value = shippingId;
  return true;
}

async function maybeAutoAdoptHabits(plan) {
  if (!habitsAutoAdoptEligible(plan)) return;
  await adoptHabitsRecommendation({ silent: true });
}

async function adoptHabitsRecommendation(options = {}) {
  const silent = Boolean(options.silent);
  if (!store.shopId || !doc.categoryId) return;
  const shippingId = habitsShippingPick.value || habitsPanel.value?.recommended_shipping_template_id || "";
  if (!shippingId) {
    if (!silent) ElMessage.warning("请选择运费模板");
    return;
  }
  habitsApplying.value = true;
  try {
    const result = await api.excelApplyHabits({
      shop_id: store.shopId,
      category_id: doc.categoryId,
      category_name: doc.categoryName || smartPlan.value.category_name || "",
      shipping_template_id: shippingId,
      template_id: habitsPanel.value?.selected_template_id || doc.templateId || "",
      apply_to: "both",
    });
    if (result.habits) {
      smartPlan.value = { ...smartPlan.value, habits: result.habits };
    }
    syncHabitsFromPlan(smartPlan.value);
    if (!silent) {
      ElMessage.success("发品习惯已保存，成稿时将自动套用");
    }
    await persistSession({ server: true });
  } catch (error) {
    habitsAutoAdoptKey = "";
    if (!silent) ElMessage.error(error.message);
  } finally {
    habitsApplying.value = false;
  }
}

async function refreshSmartPlan() {
  if (!doc.categoryId) {
    ElMessage.warning("先选叶子类目");
    return;
  }
  smartPlanError.value = "";
  try {
    await loadSmartPlan({ categoryId: doc.categoryId, categoryName: doc.categoryName, refresh: true });
    ElMessage.success(`已重新规划：需填 ${smartPlan.value.column_count || 0} 列`);
    await persistSession({ server: true });
  } catch (error) {
    if (!smartPlan.value.column_count) {
      ElMessage.error(smartPlanError.value || error.message);
    }
  }
}




function openDocCategory() {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  if (!canPickCategory.value) {
    ElMessage.warning("请先点「确定选图」，或选择「暂不上传图片」");
    return;
  }
  categoryBrowser.value = true;
}

function markReviewAiDone() {
  reviewAiSteps.value = reviewAiSteps.value.map((step) => ({
    ...step,
    status: step.status === "error" ? step.status : "done",
    detail: step.detail || "已完成",
  }));
}

function goToAuditStep() {
  if (!docGrid.rows.length) return;
  docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
  docReached.value = Math.max(docReached.value, 1);
  docStep.value = 1;
  reviewPage.value = 1;
  doc.reviewAiDone = true;
  markReviewAiDone();
  void persistSession({ server: true });
  void autoStartReviewImages();
}

function advanceDoc(index) {
  docReached.value = Math.max(docReached.value, index);
  docStep.value = index;
  void persistSession({ server: true });
  if (index === 1) void runReviewAssist(true);
}

function rowSlots(row) {
  const imageNames = String(row?.images || "")
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);
  const httpUrls = imageNames.filter((name) => /^https?:\/\//i.test(name));
  if (httpUrls.length) {
    return slotsFromLocalUrls(httpUrls);
  }
  const uploads = buildUploadMap(allUploadImageFiles());
  if (Object.keys(uploads).length && imageNames.length) {
    const matched = matchUploadFiles(row?.sku, imageNames, uploads);
    if (matched.length) {
      return slotsFromLocalUrls(matched.map(([, raw]) => URL.createObjectURL(raw)));
    }
  }
  if (row?.image_slots?.length && row.image_slots.some((slot) => slot.url)) {
    return row.image_slots;
  }
  return DEFAULT_IMAGE_SLOTS.map((slot) => ({ ...slot }));
}

function rowImageUrls(row) {
  return rowSlots(row).filter((slot) => slot.url).map((slot) => slot.url);
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
      maybeEnterAuditStep();
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
  if (status === "approved") return "已通过";
  if (status === "rejected") return "已跳过";
  if (rowAuditReady(row)) return "可成稿";
  if (!rowReady(row)) return "缺价量";
  if (rowMissingCopy(row)) return "缺文案";
  if (rowImageCount(row) < 1) return "缺图";
  return "待确认";
}

function rowStatusTone(row) {
  const status = rowAuditStatus(row);
  if (status === "approved") return "approved";
  if (status === "rejected") return "rejected";
  if (rowAuditReady(row)) return "ready";
  return "warn";
}

function rowNeedsFix(row) {
  if (rowAuditStatus(row) === "approved") return false;
  return !rowAuditReady(row);
}

function formatAuditPrice(value) {
  const raw = String(value || "").trim();
  if (!raw) return "—";
  const num = Number(raw.replace(/[^\d.]/g, ""));
  if (Number.isFinite(num) && num > 0) return num.toFixed(2);
  return raw;
}

function formatAuditCell(row, col) {
  if (!row || !col) return "";
  const value = row[col.id];
  if (col.id === "price") return formatAuditPrice(value);
  return String(value || "").trim();
}

function rowAuditReady(row) {
  return rowReady(row) && !rowMissingCopy(row) && rowImageCount(row) >= 1 && !rowHasIssues(row);
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

function batchApproveReady() {
  const targets = docGrid.rows.filter((row) => rowAuditReady(row) && rowAuditStatus(row) !== "approved");
  if (!targets.length) {
    ElMessage.info("没有可自动通过的行（需价、量、标题、关键词、至少一张图）");
    return;
  }
  targets.forEach((row) => {
    row._audit_status = "approved";
  });
  persistSession();
  ElMessage.success(`已通过 ${targets.length} 条可成稿商品`);
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

function openRowDetail(view, focusField = "") {
  rowDetailRow.value = view.row;
  rowDetailOpen.value = true;
  if (focusField) {
    rowDetailFocusField.value = focusField;
  }
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
  const added = addDocImageFiles(picked);
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
  const added = addDocImageFiles(files);
  docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
  if (added) {
    ElMessage.success(`已配对 ${added} 张图片`);
    void recheckDocGrid({ silent: true });
    persistSession();
  }
}

async function inferFieldsForRows(lines, options = {}) {
  const { silent = false } = options;
  if (!docGrid.rows.length) return { ok: true, skipped: true, reason: "no_rows" };
  if (aiServiceReady.value === false) return { ok: true, skipped: true, reason: "no_ai" };
  docInferring.value = true;
  try {
    const body = new FormData();
    body.append("shop_id", store.shopId || "");
    body.append("category_id", doc.categoryId);
    body.append("category_name", doc.categoryName || smartPlan.value.category_name || "");
    if (smartPlan.value.columns?.length) {
      body.append("plan_columns", JSON.stringify(smartPlan.value.columns));
    }
    if (docGrid.columns?.length) {
      body.append("columns", JSON.stringify(docGrid.columns));
    } else if (smartPlan.value.columns?.length) {
      body.append("columns", JSON.stringify(smartPlan.value.columns));
    }
    body.append("rows", JSON.stringify(docGrid.rows));
    body.append("lines", JSON.stringify(lines || []));
    const result = await api.excelGridInferFields(body);
    if (Array.isArray(result.rows) && result.rows.length) {
      docGrid.rows = normalizeDocRows(result.rows);
    }
    if (Array.isArray(result.columns) && result.columns.length) {
      docGrid.columns = result.columns;
    }
    await recheckDocGrid({ silent: true });
    scheduleLocalDraft();
    scheduleServerSync();
    if (!silent) {
      if (result.filled_count) {
        ElMessage.success(`已补全 ${result.filled_count} 个属性`);
      } else if (result.missing_required_cells) {
        ElMessage.warning(`仍有 ${result.missing_required_cells} 个必填属性缺依据，请补备注或手填`);
      } else {
        ElMessage.info("属性已齐");
      }
    }
    return {
      ok: true,
      filled_count: result.filled_count || 0,
      fillable_columns: result.fillable_columns || 0,
      missing_required_cells: result.missing_required_cells || 0,
    };
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
      return { ok: false, error: result.errors[0], jobs_started: result.jobs_started || 0 };
    }
    ensureGridPolling();
    await persistSession();
    if (!silent) {
      const n = result.jobs_started || 0;
      ElMessage.success(lines?.length ? `已开始为选中行出图` : `已并发提交 ${n} 行出图`);
    }
    return { ok: true, jobs_started: result.jobs_started || 0 };
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
    body.append("use_ecosystem", useEcosystemAssistant.value ? "true" : "false");
    const result = await api.excelGridRegenCopy(body);
    if (Array.isArray(result.rows) && result.rows.length) {
      docGrid.rows = normalizeDocRows(result.rows);
    }
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
  if (!docGrid.rows.length || !doc.categoryId) return { ok: true, skipped: true, reason: "no_rows" };
  if (!rowsNeedingCopy().length) {
    return { ok: true, skipped: true, reason: "has_copy", copyOk: docGrid.rows.length };
  }
  const need = rowsNeedingCopy().length;
  patchReviewStep("copy", { status: "running", detail: `共 ${need} 行` });
  return regenCopyForRows([], { silent: true });
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
      const reasoning = doc.templateReason || templateResult.suggestion?.reasoning || "";
      patchReviewStep("template", {
        status: "done",
        detail: doc.templateId
          ? `已选「${name}」`
          : reasoning || "本店尚无该类目刊登模板，可在「发品习惯 → 类目模板」添加；文案仍按国际站规则生成",
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
        if (copyResult.reason === "no_rows") {
          patchReviewStep("copy", { status: "error", detail: "无商品行" });
        } else {
          patchReviewStep("copy", { status: "done", detail: "已有文案" });
        }
      } else if (copyResult.ok) {
        patchReviewStep("copy", {
          status: "done",
          detail: `已完成 ${copyResult.copyOk || 0}/${docGrid.rows.length} 行`,
        });
      } else {
        patchReviewStep("copy", { status: "error", detail: copyResult.error || "文案生成失败" });
      }

      patchReviewStep("attrs", { status: "running", detail: "从填写表与文案补全官方属性…" });
      docGrid.rows = normalizeDocRows(applyLocalImageMatches(docGrid.rows, allUploadImageFiles()));
      const imageNeed = rowsNeedingImageJobs().length;
      const imagePromise = imageNeed
        ? generateImagesForRows([], { silent: true })
        : Promise.resolve({ ok: true, skipped: true });
      const inferPromise = inferFieldsForRows([], { silent: true });
      const [inferResult, imageResult] = await Promise.all([inferPromise, imagePromise]);
      if (inferResult.skipped) {
        if (inferResult.reason === "no_rows") {
          patchReviewStep("attrs", { status: "error", detail: "无商品行" });
        } else if (inferResult.reason === "no_ai") {
          patchReviewStep("attrs", { status: "error", detail: "需要 AI 服务" });
        } else {
          patchReviewStep("attrs", { status: "done", detail: "无可补属性列" });
        }
      } else if (inferResult.ok) {
        const filled = inferResult.filled_count || 0;
        const missing = inferResult.missing_required_cells || 0;
        if (missing) {
          patchReviewStep("attrs", { status: "error", detail: `已补 ${filled} 项，仍缺 ${missing} 个必填` });
        } else if (filled) {
          patchReviewStep("attrs", { status: "done", detail: `已补 ${filled} 项属性` });
        } else {
          patchReviewStep("attrs", { status: "done", detail: "属性已齐" });
        }
      } else {
        patchReviewStep("attrs", { status: "error", detail: inferResult.error || "推断失败" });
      }

      const matchedPhotos = docGrid.rows.filter((row) => rowImageCount(row) > 0).length;
      if (imageNeed) {
        if (imageResult.ok) {
          ensureGridPolling();
          const started = imageResult.jobs_started || rowsNeedingImageJobs().length;
          patchReviewStep("images", {
            status: "done",
            detail: `已并发提交 ${started} 行出图，审核时可继续操作`,
          });
        } else {
          patchReviewStep("images", { status: "error", detail: imageResult.error || "出图失败" });
        }
      } else if (matchedPhotos) {
        patchReviewStep("images", { status: "done", detail: `已配对 ${matchedPhotos}/${docGrid.rows.length} 行图片` });
      } else {
        patchReviewStep("images", { status: "done", detail: "图片已齐" });
      }
    }

    patchReviewStep("check", { status: "running", detail: "校验…" });
    await recheckDocGrid({ silent: true });
    if (!reviewStats.value.total) {
      patchReviewStep("check", { status: "error", detail: "无商品行" });
    } else {
      patchReviewStep("check", {
        status: "done",
        detail: `文案 ${reviewStats.value.copyOk}/${reviewStats.value.total} · 六图 ${reviewStats.value.imagesOk}/${reviewStats.value.total}`,
      });
    }
  } finally {
    reviewAssistRunning.value = false;
    void persistSession({ server: true });
    maybeEnterAuditStep();
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
  const spreadsheets = docSpreadsheetFiles.value.filter((item) => item.raw);
  const images = allUploadImageFiles();
  if (!spreadsheets.length) {
    ElMessage.warning("至少上传一个 Excel/CSV 表格（刷新页面后需重新选择文件）");
    return;
  }
  const uploadables = [...spreadsheets, ...images];
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
    doc.llmColumnManifest = result.llm_column_manifest || docGrid.columns || [];
    if (result.download_columns?.length) {
      smartPlan.value = normalizeSmartPlan({ ...smartPlan.value, columns: result.download_columns, column_count: result.download_columns.length });
    }
    docGrid.rows = normalizeDocRows(applyLocalImageMatches(result.rows || [], uploadables));
    docGrid.row_issues = result.row_issues || [];
    docGrid.warnings = result.warnings || [];
    docGrid.row_count = result.row_count || docGrid.rows.length;
    docGrid.ready_count = result.ready_count || 0;
    docGrid.source = result.source || "";
    docReached.value = Math.max(docReached.value, 1);
    patchReviewStep("service", { status: "done", detail: "解析完成" });
    void persistSession({ server: true });
    scheduleDocImageSync();
    await runReviewAssist(true);
    maybeEnterAuditStep();
    ElMessage.success(`识别到 ${docGrid.row_count} 个商品，AI 补全完成后进入审核`);
  } catch (error) {
    resetReviewAiSteps();
    ElMessage.error(error.message);
  } finally {
    docGrid.loading = false;
    parseStatus.value = "";
    void persistSession({ server: true });
  }
}

async function recheckDocGrid(options = {}) {
  const { silent = false } = options;
  if (!docGrid.rows.length) return;
  const body = new FormData();
  body.append("shop_id", store.shopId || "");
  body.append("category_id", doc.categoryId);
  body.append("image_mode", excelImageMode.value);
  if (docGrid.columns?.length) {
    body.append("columns", JSON.stringify(docGrid.columns));
  } else if (smartPlan.value.columns?.length) {
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
      await ElMessageBox.confirm("未标记通过，仍成稿全部商品？", "批量成稿", {
        confirmButtonText: "成稿",
        cancelButtonText: "取消",
        type: "warning",
      });
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
  const importColumns = docGrid.columns?.length ? docGrid.columns : smartPlan.value.columns;
  if (importColumns?.length) {
    body.append("columns", JSON.stringify(importColumns));
  }
  if (doc.templateId) {
    body.append("listing_template_id", doc.templateId);
  }
  body.append("rows", JSON.stringify(targets));
  await syncDocImagesToSession();
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
    if (!smartPlan.value.columns?.length) {
      throw new Error("还没有生成填写列，请稍候或点「重新生成」");
    }
    const categoryName = doc.categoryName || smartPlan.value.category_name || "";
    const planPayload = {
      shop_id: store.shopId,
      category_id: doc.categoryId,
      category_name: categoryName,
      columns: smartPlan.value.columns,
      reasoning: smartPlan.value.reasoning,
      tips: smartPlan.value.tips,
      guarantee: smartPlan.value.guarantee,
      covered_by_shop: smartPlan.value.covered_by_shop,
      covered_by_template: smartPlan.value.covered_by_template,
      ai_fills: smartPlan.value.ai_fills,
    };
    let blob;
    if (hasUploadablePlanImages() || selectedPhotobankList().length) {
      const form = new FormData();
      Object.entries(planPayload).forEach(([key, value]) => {
        form.append(key, typeof value === "string" ? value : JSON.stringify(value ?? []));
      });
      allUploadImageFiles().forEach((item) => {
        if (item.raw) form.append("files", item.raw, item.name);
      });
      const bank = selectedPhotobankList();
      if (bank.length) form.append("photobank_images", JSON.stringify(bank));
      blob = await api.excelSmartTemplateFromPlanFiles(form);
    } else {
      blob = await api.excelSmartTemplateFromPlan(planPayload);
    }
    const safeName = (categoryName || doc.categoryId).replace(/[/\\?%*:|"<>]/g, "-");
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `智能批量上品-${safeName}.xlsx`;
    anchor.click();
    URL.revokeObjectURL(url);
    ElMessage.success(
      hasUploadablePlanImages() || selectedPhotobankList().length
        ? `填写表已开始下载（${smartPlan.value.column_count || smartPlan.value.columns.length} 列，已嵌入商品图）`
        : `填写表已开始下载（${smartPlan.value.column_count || smartPlan.value.columns.length} 列）`,
    );
  } catch (error) {
    ElMessage.error(error.message || "下载失败");
  } finally {
    docTemplateDownloading.value = false;
  }
}


async function pickCategory(node) {
  await ensureFeedSession({ quiet: true });
  if (!canPickCategory.value) {
    ElMessage.warning("请先完成第 1 步：确定选图或跳过");
    return;
  }
  const categoryId = node.category_id;
  const categoryName = node.path_label || node.label || node.name || node.cn_name || "";
  categoryBrowser.value = false;

  if (doc.categoryId === categoryId && hasSmartPlanForCategory(categoryId)) {
    ElMessage.success(`已选「${smartPlan.value.category_name || categoryName}」`);
    await persistSession({ server: true });
    return;
  }

  doc.categoryId = categoryId;
  doc.categoryName = categoryName;

  const localCached = hasUploadablePlanImages() ? null : loadLocalSmartPlan(categoryId);
  if (localCached?.columns?.length && !isCoreOnlySmartPlan(localCached)) {
    applySmartPlan({ ...localCached, cached: true }, categoryId);
    try {
      await store.ensureShops();
      void loadSmartPlan({ categoryId, categoryName, background: true });
      ElMessage.success(`已选「${localCached.category_name || categoryName}」`);
      await persistSession({ server: true });
      return;
    } catch (error) {
      ElMessage.warning(`类目已选，后台刷新规划失败：${error.message}`);
      await persistSession({ server: true });
      return;
    }
  }

  try {
    await store.ensureShops();
    await loadSmartPlan({ categoryId, categoryName, refresh: isCoreOnlySmartPlan(localCached) });
    if (smartPlan.value.column_count) {
      ElMessage.success(`已选「${smartPlan.value.category_name || categoryName}」`);
    } else if (smartPlanError.value) {
      ElMessage.error(smartPlanError.value);
    }
    await persistSession({ server: true });
  } catch (error) {
    if (smartPlan.value.column_count) {
      ElMessage.warning(`类目已选，但规划异常：${error.message}`);
    } else {
      ElMessage.error(smartPlanError.value || error.message);
    }
  }
}

onUnmounted(() => {
  clearInterval(docTimer);
  clearInterval(gridPollTimer);
  clearTimeout(localDraftTimer);
  clearTimeout(serverSyncTimer);
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
.habits-panel {
  border-color: var(--accent-line);
}
.habits-checks {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: grid;
  gap: 8px;
}
.habits-checks li {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--gray3);
}
.habits-checks li.is-ok {
  border-left: 3px solid #16a34a;
}
.habits-checks li.is-warn {
  border-left: 3px solid #d97706;
}
.habits-value {
  color: var(--muted);
  text-align: right;
}
.habits-pick {
  margin-top: 14px;
}
.habits-actions {
  margin-top: 12px;
}
.habits-foot {
  margin: 10px 0 0;
  font-size: 13px;
}
.plan-badge.is-ok {
  background: #dcfce7;
  color: #166534;
}
.plan-badge.is-warn {
  background: #fef3c7;
  color: #92400e;
}
.audit-habits-strip {
  padding: 8px 12px 0;
  font-size: 13px;
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

.audit-ai-timeline-inline {
  margin: 0 0 12px;
  max-width: none;
}

.eco-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: 12px;
  font-size: 13px;
  color: var(--muted, #666);
  cursor: pointer;
  user-select: none;
}

.ai-timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
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
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--panel);
}

.photobank-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.photobank-actions,
.image-setup-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.image-setup-badge {
  margin: 12px 0;
  padding: 10px 12px;
  border-radius: var(--radius);
  font-size: 14px;
}

.image-setup-badge.is-confirmed {
  background: #ecfdf3;
  color: #067647;
  border: 1px solid #abefc6;
}

.image-setup-badge.is-skipped {
  background: var(--gray3);
  color: var(--ink-2);
  border: 1px solid var(--line);
}

.link-btn {
  margin-left: 10px;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  text-decoration: underline;
  cursor: pointer;
  font: inherit;
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

.vision-preview {
  margin-top: 16px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--gray3);
}

.vision-preview h4 {
  margin: 0 0 8px;
  font-size: 14px;
}

.vision-preview ul {
  margin: 0;
  padding-left: 18px;
  color: var(--ink-2);
  font-size: 13px;
}

.vision-preview li + li {
  margin-top: 6px;
}

.plan-panel-error {
  margin-top: 16px;
  padding: 12px 14px;
  border: 1px solid #fecdca;
  border-radius: var(--radius);
  background: #fef3f2;
  color: #b42318;
}

.plan-panel-error p {
  margin: 0 0 10px;
}

.plan-source-hint {
  margin: 8px 0 10px;
  font-size: 13px;
  line-height: 1.55;
}

.plan-badge-muted {
  background: var(--gray3);
  color: var(--ink-2);
}

.plan-bridge-panel {
  margin-top: 16px;
  border: 1px solid var(--accent-line);
  background: var(--accent-wash);
}

.plan-bridge-label {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-2);
}

.ai-timeline-elapsed {
  margin-left: auto;
  font-size: 12px;
  color: var(--muted);
  font-weight: normal;
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

.audit-guide {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.audit-guide-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: var(--surface);
}

.audit-guide-num {
  flex: 0 0 24px;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: var(--accent-wash);
  color: var(--accent-text);
  font-size: 12px;
  font-weight: 700;
  line-height: 24px;
  text-align: center;
}

.audit-guide-step b {
  display: block;
  margin-bottom: 2px;
  font-size: 13px;
}

.audit-guide-step span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
}

.audit-context-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  margin-bottom: 10px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: calc(var(--radius) + 2px);
  background: var(--gray3);
  font-size: 12px;
}

.audit-context-strip b {
  color: var(--ink);
}

.audit-context-strip .muted {
  color: var(--muted);
}

.audit-table-full {
  min-width: max(100%, 960px);
}

.audit-table-full .col-field {
  min-width: 108px;
  max-width: 180px;
}

.audit-table-full .sticky-col {
  position: sticky;
  left: 0;
  z-index: 2;
  background: var(--surface);
}

.audit-table-full .sticky-col-right {
  position: sticky;
  right: 0;
  z-index: 2;
  background: var(--surface);
}

.audit-table-scroll {
  overflow-x: auto;
}

.audit-summary-strip .is-good b {
  color: #15803d;
}

.audit-summary-strip .is-warn {
  color: #b45309;
}

.audit-moq {
  color: var(--muted);
  font-size: 12px;
}

.audit-moq.is-warn {
  color: #b45309;
}

.audit-drawer-ok {
  margin: 0 0 12px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #ecfdf5;
  color: #166534;
  font-size: 13px;
}

.audit-status.is-ready {
  color: #15803d;
  background: #ecfdf5;
}

.audit-status.is-warn {
  color: #b45309;
  background: #fffbeb;
}

.audit-table tr.is-needs-fix td {
  background: #fffbeb;
}

.audit-table tr.is-approved td {
  background: #f0fdf4;
}

.audit-page-head {
  padding: 4px 0 20px;
}

.audit-page-head-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.audit-page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--ink);
}

.audit-ai-banner {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  background: #e6f4ff;
  color: #1677ff;
  font-size: 13px;
}

.audit-table .col-product {
  min-width: 200px;
}

.audit-table .col-title {
  min-width: 180px;
  max-width: 240px;
}

.audit-table .col-keywords {
  min-width: 160px;
  max-width: 220px;
}

.audit-table .col-price {
  white-space: nowrap;
}

.audit-table .col-images {
  min-width: 120px;
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

.audit-summary-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  padding: 10px 16px;
  border-bottom: 1px solid #f0f0f0;
  font-size: 13px;
  color: var(--muted);
}

.audit-summary-strip b {
  color: var(--ink);
}

.audit-summary-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.audit-drawer-hint {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--muted);
}

.audit-drawer-issues {
  margin: 0 0 14px;
  padding-left: 18px;
  color: #cf1322;
  font-size: 13px;
}

.audit-drawer-issues li + li {
  margin-top: 4px;
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
  background: transparent;
  border-bottom-color: #1677ff;
}

.audit-prep-panel {
  margin-top: 8px;
  padding: 20px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fff;
}

.audit-prep-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-bottom: 16px;
}

.audit-prep-head .audit-page-title,
.audit-prep-head .audit-subtitle {
  width: 100%;
  margin: 0;
}

.audit-prep-head .ai-timeline-badge {
  margin-left: auto;
}

.audit-table tr.is-selected td {
  background: #f0f7ff;
}

.audit-table tr.is-approved td,
.audit-table tr.is-rejected td {
  background: #fff;
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
