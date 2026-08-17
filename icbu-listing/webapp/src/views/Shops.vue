<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>店铺</h2>
        <p class="muted">跳转阿里官方页面授权。每个店填一次默认值，后面不用再问。</p>
      </div>
      <div>
        <el-button v-if="showDevBind" text @click="bindEnv">本地接入</el-button>
        <el-button type="primary" @click="authorize">授权新店铺</el-button>
      </div>
    </div>

    <el-alert
      v-if="oauthError"
      type="error"
      show-icon
      title="店铺授权没有完成"
      :description="oauthError"
      style="margin-bottom: 14px"
      @close="oauthError = ''"
    />

    <el-table :data="store.shops" v-loading="loading">
      <el-table-column label="店铺" min-width="200">
        <template #default="{ row }">
          <div class="record">
            <span class="record-mark">{{ (row.name || "店").slice(0, 1) }}</span>
            <div>
              <div>{{ row.name }}</div>
              <div class="muted">{{ row.account || "已授权" }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <span v-if="row.status === 'active' && row.connected" class="status-pill green">已授权</span>
          <span v-else-if="row.status === 'expired'" class="status-pill yellow">需重新授权</span>
          <span v-else class="status-pill red">异常</span>
        </template>
      </el-table-column>
      <el-table-column label="发布模式" width="130">
        <template #default="{ row }">
          <span class="status-pill">{{ row.publish_mode === "online" ? "直接上架" : "只发草稿" }}</span>
        </template>
      </el-table-column>
      <el-table-column label="默认设置" min-width="280">
        <template #default="{ row }">
          <span class="muted">
            产地 {{ shown(row, "origin") }} · 单位 {{ shown(row, "priceUnit") }} · 运费 {{ shown(row, "shippingTemplateId") || "买卖双方协商" }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" align="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="edit(row)">店铺默认</el-button>
          <el-button text type="primary" @click="use(row)">设为当前</el-button>
          <el-button text type="danger" @click="unbind(row)">解绑</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty">还没有店铺。点右上角「授权新店铺」，跳转阿里官方页面确认即可。</div>
      </template>
    </el-table>

    <el-drawer v-model="drawer" size="460px" :title="`${editing?.name || ''} · 店铺默认`">
      <p class="muted" style="margin-bottom: 16px">
        这些是后面成稿的依据。交易和物流信息 AI 不猜。填一次，每条商品自动套。
      </p>
      <el-form v-if="editing" v-loading="optionsLoading" label-width="110px">
        <el-form-item label="店铺名">
          <el-input v-model="editing.name" />
        </el-form-item>
        <el-form-item label="发布模式">
          <el-radio-group v-model="editing.publish_mode">
            <el-radio-button value="draft">只发草稿</el-radio-button>
            <el-radio-button value="online">直接上架</el-radio-button>
          </el-radio-group>
          <div class="muted" style="margin-top: 6px">先用草稿模式跑通，确认无误再切上架。</div>
        </el-form-item>

        <p v-if="optionSource.category_name" class="muted" style="margin: 0 0 12px">
          选项来自官方发布规则（{{ optionSource.category_name }}），按官方选项选就行。
        </p>

        <el-form-item v-for="field in pickable" :key="field.key" :label="field.label">
          <el-select
            v-model="editing.defaults[field.key]"
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

        <el-form-item label="包装尺寸">
          <div style="display: flex; gap: 8px">
            <el-input v-model="editing.defaults.pkgLength" placeholder="长 cm" />
            <el-input v-model="editing.defaults.pkgWidth" placeholder="宽 cm" />
            <el-input v-model="editing.defaults.pkgHeight" placeholder="高 cm" />
          </div>
        </el-form-item>
        <el-form-item label="包装重量">
          <el-input v-model="editing.defaults.pkgWeight" placeholder="kg" />
        </el-form-item>
        <el-form-item label="发货期">
          <el-input v-model="editing.defaults.ladderPeriod" placeholder="15" />
          <div class="muted" style="margin-top: 6px">天数。交期必须是你定的，AI 不准编。</div>
        </el-form-item>
        <el-form-item label="品牌">
          <el-input v-model="editing.defaults.brand" placeholder="没有就留空" />
        </el-form-item>

        <p v-if="unsupported.length" class="muted" style="margin: 0 0 14px">
          这个店的类目没有{{ unsupported.map((item) => item.label).join("、") }}，官方规则里就没有这些字段，不用填。
        </p>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </el-form>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const route = useRoute();
const loading = ref(false);
const saving = ref(false);
const drawer = ref(false);
const editing = ref(null);
const showDevBind = ref(["localhost", "127.0.0.1"].includes(window.location.hostname));
const oauthError = ref("");
const optionsLoading = ref(false);
const optionSource = ref({ category_name: "", fields: [] });
const pickedLabels = ref({});

const pickable = computed(() => (optionSource.value.fields || []).filter((item) => item.kind === "select"));
const unsupported = computed(() => (optionSource.value.fields || []).filter((item) => item.kind === "unsupported"));

function shown(shop, key) {
  return shop.defaults?.labels?.[key] ?? shop.defaults?.[key] ?? "";
}

function splitValues(value) {
  if (Array.isArray(value)) return value;
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function rememberLabel(field) {
  const chosen = editing.value.defaults[field.key];
  const picked = (Array.isArray(chosen) ? chosen : [chosen])
    .map((value) => field.options.find((option) => option.value === value)?.label)
    .filter(Boolean);
  pickedLabels.value[field.key] = picked.join("、");
}

async function loadOptions(shopId) {
  optionsLoading.value = true;
  try {
    optionSource.value = await api.shopDefaultOptions(shopId);
    // The form binds official values; seed the snapshot from what is saved.
    // Multi-selects need an array here, but defaults stay a comma string so
    // the publish pipeline keeps reading them the way it always has.
    for (const field of pickable.value) {
      editing.value.defaults[field.key] = field.multiple ? splitValues(field.value) : field.value;
      rememberLabel(field);
    }
  } catch (error) {
    optionSource.value = { category_name: "", fields: [] };
    ElMessage.warning(`拉不到官方选项，先手填：${error.message}`);
  } finally {
    optionsLoading.value = false;
  }
}

if (route.query.alibaba === "error") {
  oauthError.value =
    route.query.message ||
    "阿里没有回传原因。最常见的是回调地址没在开放平台注册：控制台里填的必须和本服务的 /api/v1/alibaba/oauth/callback 完全一致。";
}

async function reload() {
  loading.value = true;
  try {
    await store.loadShops();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await reload();
  if (route.query.alibaba === "connected" && store.shops.length) {
    const newest = store.shops[store.shops.length - 1];
    ElMessage.success("店铺已授权。先填一次默认值，之后每条商品不用再问。");
    edit(newest);
  }
});

async function authorize() {
  try {
    const { url } = await api.oauthStart();
    window.location.href = url;
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function bindEnv() {
  try {
    const shop = await api.bindEnvShop("环境店铺");
    store.selectShop(shop.id);
    await reload();
    ElMessage.success("已接入。先填一次店铺默认，之后每条商品不用再问。");
    edit(store.shops.find((item) => item.id === shop.id) || shop);
  } catch (error) {
    ElMessage.error(error.message);
  }
}

function edit(shop) {
  editing.value = JSON.parse(JSON.stringify(shop));
  pickedLabels.value = { ...(editing.value.defaults?.labels || {}) };
  drawer.value = true;
  loadOptions(shop.id);
}

function use(shop) {
  store.selectShop(shop.id);
  ElMessage.success(`当前店铺切到「${shop.name}」`);
}

async function save() {
  saving.value = true;
  try {
    const defaults = { ...editing.value.defaults };
    for (const field of pickable.value) {
      if (field.multiple) defaults[field.key] = splitValues(defaults[field.key]).join(",");
    }
    await api.saveDefaults(editing.value.id, {
      defaults,
      labels: pickedLabels.value,
      publish_mode: editing.value.publish_mode,
      name: editing.value.name,
    });
    drawer.value = false;
    await reload();
    ElMessage.success("已保存");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function unbind(shop) {
  try {
    await ElMessageBox.confirm(`解绑「${shop.name}」会删掉它的草稿和发布记录，确定吗？`, "解绑店铺", {
      type: "warning",
    });
  } catch {
    return;
  }
  await api.unbindShop(shop.id);
  await reload();
  ElMessage.success("已解绑");
}
</script>
