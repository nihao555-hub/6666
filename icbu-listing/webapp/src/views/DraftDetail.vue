<template>
  <div class="page" v-loading="loading">
    <div class="page-head">
      <div>
        <h2>核对 · {{ draft.sku || draft.title || "未命名" }}</h2>
        <p class="muted">
          不能保证 AI 零出错。改完点「审过了」，没审过不能发。预估质量
          <b>{{ draft.quality?.score ?? "—" }}</b> / 5.0
        </p>
      </div>
      <div>
        <el-button @click="$router.push('/drafts')">返回商品</el-button>
        <el-button type="primary" :loading="publishing" :disabled="!canPublish" @click="publish">
          {{ publishLabel }}
        </el-button>
      </div>
    </div>

    <el-row :gutter="14">
      <el-col :span="16">
        <div class="card" v-if="issues.length">
          <h3>需要你确认（{{ issues.length }}）</h3>
          <div v-for="issue in issues" :key="issue.path || issue.field_id" class="issue">
            <div class="issue-head">
              <i class="dot" :class="issue.level"></i>
              <b>{{ issue.field_name }}</b>
              <span class="muted">{{ issue.message }}</span>
            </div>
            <div v-if="issue.options?.length" class="issue-fix">
              <el-select
                v-model="attrFix[issue.field_id]"
                filterable
                placeholder="选一个官方选项"
                style="width: 320px"
                @change="(value) => fixAttribute(issue, value)"
              >
                <el-option v-for="option in issue.options" :key="option.value" :label="option.label" :value="option.value" />
              </el-select>
            </div>
            <div v-else-if="issue.field_id === 'category'" class="issue-fix">
              <el-select
                v-model="categoryChoice"
                filterable
                placeholder="换一个类目"
                style="width: 420px"
                @change="changeCategory"
              >
                <el-option
                  v-for="item in draft.category_candidates || []"
                  :key="item.category_id"
                  :label="item.label"
                  :value="item.category_id"
                />
              </el-select>
              <el-button text type="primary" @click="browser = true">浏览完整类目树</el-button>
            </div>
          </div>
        </div>
        <el-alert
          v-else-if="draft.reviewed"
          type="success"
          show-icon
          :closable="false"
          title="已经核对过，没有红项，可以发到店里"
          style="margin-bottom: 14px"
        />
        <el-alert
          v-else
          type="warning"
          show-icon
          :closable="false"
          title="还没人看过。标题、类目、规格都对一下，再点审过了。"
          style="margin-bottom: 14px"
        />

        <div class="card">
          <h3>AI 填的文案，不对就改</h3>
          <el-form label-width="90px" style="margin-top: 12px">
            <el-form-item label="英文标题">
              <el-input v-model="title" type="textarea" :rows="2" />
              <div class="muted">
                {{ titleTooLong ? "标题偏长，发布时可能被拒。" : "手改过的不会被重新成稿盖掉。" }}
                <span v-if="sourceOf('productTitle')" class="status-pill" style="margin-left: 6px">{{ sourceOf("productTitle").label }}</span>
              </div>
            </el-form-item>
            <el-form-item label="关键词">
              <el-input v-model="keywords" placeholder="用逗号分隔，最多 3 个" />
              <span v-if="sourceOf('productKeywords')" class="status-pill">{{ sourceOf("productKeywords").label }}</span>
            </el-form-item>
            <el-form-item label="卖点描述">
              <el-input v-model="highlights" type="textarea" :rows="4" />
              <span v-if="sourceOf('textDesc')" class="status-pill">{{ sourceOf("textDesc").label }}</span>
            </el-form-item>
          </el-form>
        </div>

        <div class="card" v-if="attrGroups.length">
          <h3>规格属性，不对就改</h3>
          <p class="muted" style="margin: 6px 0 12px">这些是 AI 按官方选项填的。选错了发得出去，买家看到的却是错货。</p>
          <div v-for="group in attrGroups" :key="group.name" class="attr-group">
            <div class="attr-group-name">{{ group.name }}</div>
            <el-form label-width="120px">
              <el-form-item v-for="field in group.fields" :key="field.id">
                <template #label>
                  <span :class="{ required: field.required }">{{ field.name }}</span>
                </template>
                <el-select
                  v-if="field.kind === 'select' || field.kind === 'multiselect'"
                  v-model="attrValues[fieldKey(field)]"
                  filterable
                  clearable
                  :multiple="field.kind === 'multiselect'"
                  placeholder="选官方选项"
                  style="width: 100%"
                >
                  <el-option v-for="option in field.options" :key="option.value" :label="option.label" :value="option.value" />
                </el-select>
                <el-input v-else v-model="attrValues[fieldKey(field)]" />
                <span v-if="field.source" class="status-pill" style="margin-left: 8px">{{ field.source.label }}</span>
              </el-form-item>
            </el-form>
          </div>
        </div>

        <div class="card">
          <h3>价格和起订量</h3>
          <el-form label-width="90px" style="margin-top: 12px">
            <el-form-item label="单价">
              <el-input v-model="price" style="width: 200px" />
            </el-form-item>
            <el-form-item label="起订量">
              <el-input v-model="moq" style="width: 200px" />
            </el-form-item>
            <el-form-item label="核对备注">
              <el-input v-model="auditNote" type="textarea" :rows="2" placeholder="给自己看，比如：颜色改过、类目确认过" />
            </el-form-item>
            <el-button :loading="saving" @click="save(false)">先保存修改</el-button>
            <el-button type="primary" :loading="saving" :disabled="hasRed" @click="save(true)">
              {{ hasRed ? "先改红项" : "审过了，可以发" }}
            </el-button>
          </el-form>
        </div>
      </el-col>

      <el-col :span="8">
        <div class="card">
          <h3>核对状态</h3>
          <p style="margin: 8px 0 4px">
            <span class="status-pill" :class="draft.reviewed ? 'green' : 'yellow'">
              {{ draft.reviewed ? "已审过" : "待核对" }}
            </span>
          </p>
          <p class="muted" v-if="draft.audit?.reviewed_at">{{ draft.audit.reviewed_at.replace("T", " ").slice(0, 16) }} 看过</p>
          <p class="muted" v-else>打开改完，点「审过了」才会进可发名单。</p>
          <p class="muted" v-if="draft.audit?.note" style="margin-top: 8px">备注：{{ draft.audit.note }}</p>
        </div>

        <div class="card">
          <h3>类目</h3>
          <p style="margin: 8px 0 4px">{{ draft.category_name || "待定" }}</p>
          <span class="muted">{{ percent }} 确定</span>
          <div style="margin-top: 10px">
            <el-button size="small" @click="browser = true">改类目</el-button>
            <el-button size="small" :loading="saving" @click="regenerate">按当前类目重新成稿</el-button>
            <div class="muted" style="margin-top: 8px">重新成稿会清掉「已审过」，手改和表里填的字段会留着。</div>
          </div>
        </div>

        <div class="card">
          <h3>产品图</h3>
          <div class="thumbs">
            <img v-for="image in draft.images || []" :key="image.file_id" :src="image.preview" class="thumb big" />
          </div>
        </div>
      </el-col>
    </el-row>

    <CategoryPicker v-model="browser" @pick="pickCategory" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import CategoryPicker from "../components/CategoryPicker.vue";
import { api } from "../api";

const route = useRoute();
const router = useRouter();
const draft = ref({});
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const browser = ref(false);
const attrFix = ref({});
const categoryChoice = ref("");
const attrValues = reactive({});

const title = ref("");
const keywords = ref("");
const highlights = ref("");
const price = ref("");
const moq = ref("");
const auditNote = ref("");

const issues = computed(() => draft.value.issues || []);
const hasRed = computed(() => issues.value.some((item) => item.level === "red"));
const canPublish = computed(() => !hasRed.value && Boolean(draft.value.reviewed));
const percent = computed(() => `${Math.round((draft.value.category_confidence || 0) * 100)}%`);
const titleTooLong = computed(() => new TextEncoder().encode(title.value || "").length > 128);
const publishLabel = computed(() => {
  if (hasRed.value) return "先改红项";
  if (!draft.value.reviewed) return "先审过再发";
  return draft.value.status === "published" ? "再发到店里" : "发到店里";
});

const attrGroups = computed(() => {
  const groups = [];
  const seen = new Map();
  for (const field of draft.value.audit_fields || []) {
    if (!field.group && field.id !== "brand") continue;
    const name = field.group_name || "属性";
    if (!seen.has(name)) {
      const group = { name, fields: [] };
      seen.set(name, group);
      groups.push(group);
    }
    seen.get(name).fields.push(field);
  }
  return groups;
});

function fieldKey(field) {
  return field.group ? `${field.group}.${field.id}` : field.id;
}

function sourceOf(key) {
  return draft.value.sources?.[key] || null;
}

function hydrate(next) {
  draft.value = next;
  const values = next.values || {};
  title.value = values.productTitle || next.title || "";
  keywords.value = Object.values(values.productKeywords || {}).join(", ");
  highlights.value = values.textDesc || "";
  price.value = next.price || "";
  moq.value = next.moq || "";
  auditNote.value = next.audit?.note || "";
  Object.keys(attrValues).forEach((key) => delete attrValues[key]);
  for (const field of next.audit_fields || []) {
    if (!field.group && field.id !== "brand") continue;
    attrValues[fieldKey(field)] = field.value ?? "";
  }
}

async function load() {
  loading.value = true;
  try {
    hydrate(await api.draft(route.params.id));
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function collectValues() {
  const values = { ...(draft.value.values || {}) };
  values.productTitle = title.value;
  values.textDesc = highlights.value;
  const list = keywords.value.split(/[,，]/).map((item) => item.trim()).filter(Boolean);
  if (list.length) {
    values.productKeywords = Object.fromEntries(list.map((item, index) => [`productKeywords_${index}`, item]));
  }
  for (const field of draft.value.audit_fields || []) {
    const key = fieldKey(field);
    if (!(key in attrValues)) continue;
    if (field.group) {
      values[field.group] = { ...(values[field.group] || {}), [field.id]: attrValues[key] };
    } else {
      values[field.id] = attrValues[key];
    }
  }
  return values;
}

async function save(reviewed) {
  saving.value = true;
  try {
    hydrate(
      await api.patchDraft(draft.value.id, {
        values: collectValues(),
        price: price.value,
        moq: moq.value,
        reviewed,
        audit_note: auditNote.value,
      }),
    );
    ElMessage.success(reviewed ? "已审过，可以发到店里" : "已保存并重新校验");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function fixAttribute(issue, value) {
  const group = issue.path.split(".")[0];
  const values = { ...(draft.value.values || {}) };
  values[group] = { ...(values[group] || {}), [issue.field_id]: value };
  hydrate(await api.patchDraft(draft.value.id, { values }));
  ElMessage.success(`${issue.field_name} 已确认`);
}

async function pickCategory(node) {
  browser.value = false;
  await applyCategory(node.category_id);
}

async function changeCategory(categoryId) {
  await applyCategory(categoryId);
}

async function applyCategory(categoryId) {
  saving.value = true;
  try {
    hydrate(await api.patchDraft(draft.value.id, { category_id: categoryId }));
    ElMessage.success("已按新类目重新成稿，请再核对一次");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function regenerate() {
  saving.value = true;
  try {
    hydrate(await api.patchDraft(draft.value.id, { regenerate: true }));
    ElMessage.success("已重新成稿，请再核对一次");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function publish() {
  publishing.value = true;
  try {
    const job = await api.publishDraft(draft.value.id);
    if (job.status === "success") {
      ElMessage.success(job.product_id ? "已发布到国际站" : "已发到官方草稿箱");
      router.push("/queue");
    } else {
      ElMessage.error(job.error || "发布失败");
      await load();
    }
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    publishing.value = false;
  }
}
</script>

<style scoped>
.issue {
  padding: 10px 0;
  border-bottom: 1px dashed var(--border);
}

.issue:last-child {
  border-bottom: none;
}

.issue-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.issue-fix {
  margin: 8px 0 0 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.thumb.big {
  width: 78px;
  height: 78px;
}

.attr-group + .attr-group {
  margin-top: 16px;
}

.attr-group-name {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.required::after {
  content: " *";
  color: var(--red);
}
</style>
