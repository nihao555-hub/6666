<template>
  <div class="page" v-loading="loading">
    <div class="page-head">
      <div>
        <h2>审稿 · {{ draft.sku || draft.id?.slice(0, 8) }}</h2>
        <p class="muted">只有红黄项需要你动手。绿的已经校验过，折叠在下面。</p>
      </div>
      <div>
        <el-button @click="$router.push('/drafts')">返回草稿箱</el-button>
        <el-button type="primary" :loading="publishing" :disabled="hasRed" @click="publish">
          {{ hasRed ? "先处理红项" : "发布" }}
        </el-button>
      </div>
    </div>

    <el-row :gutter="14">
      <el-col :span="16">
        <div class="card" v-if="issues.length">
          <h3>需要你确认（{{ issues.length }}）</h3>
          <div v-for="issue in issues" :key="issue.path" class="issue">
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
        <el-alert v-else type="success" show-icon :closable="false" title="没有待处理项，可以直接发布" style="margin-bottom: 14px" />

        <div class="card">
          <h3>商品内容</h3>
          <el-form label-width="90px" style="margin-top: 12px">
            <el-form-item label="英文标题">
              <el-input v-model="title" type="textarea" :rows="2" />
              <div class="muted">
                {{ titleBytes }} / 128 字节。
                <el-tag v-if="sourceOf('productTitle')" size="small" :type="sourceType('productTitle')" style="margin-left: 6px">
                  {{ sourceOf('productTitle').label }}
                </el-tag>
              </div>
            </el-form-item>
            <el-form-item label="关键词">
              <el-input v-model="keywords" placeholder="用逗号分隔" />
              <el-tag v-if="sourceOf('productKeywords')" size="small" :type="sourceType('productKeywords')" style="margin-top: 6px">
                {{ sourceOf('productKeywords').label }}
              </el-tag>
            </el-form-item>
            <el-form-item label="卖点描述">
              <el-input v-model="highlights" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item label="单价">
              <el-input v-model="price" style="width: 200px" />
              <el-tag v-if="sourceOf('ladderPrice')" size="small" :type="sourceType('ladderPrice')" style="margin-left: 8px">
                {{ sourceOf('ladderPrice').label }}
              </el-tag>
            </el-form-item>
            <el-form-item label="起订量">
              <el-input v-model="moq" style="width: 200px" />
              <el-tag v-if="sourceOf('minOrderQuantity')" size="small" :type="sourceType('minOrderQuantity')" style="margin-left: 8px">
                {{ sourceOf('minOrderQuantity').label }}
              </el-tag>
            </el-form-item>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </el-form>
        </div>

        <div class="card">
          <el-collapse>
            <el-collapse-item title="系统已经填好的字段（按官方 schema 校验通过）" name="values">
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item v-for="(value, key) in flatValues" :key="key" :label="key">
                  {{ value }}
                </el-descriptions-item>
              </el-descriptions>
            </el-collapse-item>
            <el-collapse-item title="AI 看图识别结果" name="ai">
              <pre class="raw">{{ JSON.stringify(draft.ai?.understanding || {}, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-col>

      <el-col :span="8">
        <div class="card">
          <h3>类目</h3>
          <p style="margin: 8px 0 4px">{{ draft.category_name || "待定" }}</p>
          <span class="muted">ID {{ draft.category_id || "—" }} · 置信度 {{ percent }}</span>
          <div style="margin-top: 10px">
            <el-button size="small" @click="browser = true">改类目</el-button>
            <el-button size="small" :loading="saving" @click="regenerate">按当前类目重新成稿</el-button>
            <div class="muted" style="margin-top: 8px">手改和 Excel 填过的字段会保留，不会被 AI 盖掉。</div>
          </div>
        </div>

        <div class="card">
          <h3>图片（已进图片银行）</h3>
          <div class="thumbs">
            <img v-for="image in draft.images || []" :key="image.file_id" :src="image.preview" class="thumb big" />
          </div>
        </div>
      </el-col>
    </el-row>

    <el-dialog v-model="browser" title="选择类目" width="640px">
      <div class="muted" style="margin-bottom: 10px">
        <span v-for="(node, index) in path" :key="node.category_id">
          <el-link type="primary" @click="openNode(node.category_id)">{{ node.name }}</el-link>
          <span v-if="index < path.length - 1"> / </span>
        </span>
        <el-link v-if="path.length" type="info" style="margin-left: 8px" @click="openNode('0')">回到顶层</el-link>
      </div>
      <el-table :data="children" height="360" @row-click="(row) => openNode(row.category_id)">
        <el-table-column label="类目" min-width="240">
          <template #default="{ row }">
            {{ row.label }}
            <el-tag v-if="row.is_leaf" size="small" type="success" style="margin-left: 6px">可发布</el-tag>
          </template>
        </el-table-column>
        <el-table-column width="110" align="right">
          <template #default="{ row }">
            <el-button v-if="row.is_leaf" text type="primary" @click.stop="pickCategory(row)">选这个</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const route = useRoute();
const router = useRouter();
const draft = ref({});
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const browser = ref(false);
const children = ref([]);
const path = ref([]);
const attrFix = ref({});
const categoryChoice = ref("");

const title = ref("");
const keywords = ref("");
const highlights = ref("");
const price = ref("");
const moq = ref("");

const issues = computed(() => draft.value.issues || []);
const hasRed = computed(() => issues.value.some((item) => item.level === "red"));
const percent = computed(() => `${Math.round((draft.value.category_confidence || 0) * 100)}%`);
const titleBytes = computed(() => new TextEncoder().encode(title.value || "").length);

function sourceOf(key) {
  return draft.value.sources?.[key] || null;
}

function sourceType(key) {
  const origin = sourceOf(key)?.origin;
  return { user: "danger", excel: "warning", ai: "success", template: "info", shop: "", system: "info" }[origin] || "info";
}

const flatValues = computed(() => {
  const output = {};
  const walk = (value, prefix) => {
    if (value && typeof value === "object" && !Array.isArray(value) && !("$value" in value)) {
      Object.entries(value).forEach(([key, item]) => walk(item, prefix ? `${prefix}.${key}` : key));
    } else if (Array.isArray(value)) {
      output[prefix] = JSON.stringify(value).slice(0, 120);
    } else if (value && typeof value === "object") {
      output[prefix] = String(value.$value);
    } else {
      output[prefix] = String(value);
    }
  };
  walk(draft.value.values || {}, "");
  return output;
});

async function load() {
  loading.value = true;
  try {
    draft.value = await api.draft(route.params.id);
    const values = draft.value.values || {};
    title.value = values.productTitle || draft.value.title || "";
    keywords.value = Object.values(values.productKeywords || {}).join(", ");
    highlights.value = values.textDesc || "";
    price.value = draft.value.price || "";
    moq.value = draft.value.moq || "";
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await load();
  await openNode("0");
});

async function save() {
  saving.value = true;
  try {
    const values = { ...(draft.value.values || {}) };
    values.productTitle = title.value;
    values.textDesc = highlights.value;
    const list = keywords.value.split(/[,，]/).map((item) => item.trim()).filter(Boolean);
    if (list.length) {
      values.productKeywords = Object.fromEntries(list.map((item, index) => [`productKeywords_${index}`, item]));
    }
    draft.value = await api.patchDraft(draft.value.id, {
      values,
      price: price.value,
      moq: moq.value,
    });
    ElMessage.success("已保存并重新校验");
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
  draft.value = await api.patchDraft(draft.value.id, { values });
  ElMessage.success(`${issue.field_name} 已确认`);
}

async function openNode(parent) {
  if (!store.shopId) return;
  try {
    const data = await api.categories(store.shopId, parent);
    children.value = data.children;
    path.value = data.path;
  } catch (error) {
    ElMessage.error(error.message);
  }
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
    draft.value = await api.patchDraft(draft.value.id, { category_id: categoryId });
    await load();
    ElMessage.success("已按新类目重新成稿");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function regenerate() {
  saving.value = true;
  try {
    draft.value = await api.patchDraft(draft.value.id, { regenerate: true });
    await load();
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
      ElMessage.success(`发布成功，商品 ID ${job.product_id || "已进草稿箱"}`);
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

.raw {
  max-height: 320px;
  overflow: auto;
  background: #f7f8fa;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
}
</style>
