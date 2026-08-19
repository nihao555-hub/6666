<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>店铺</h2>
        <p class="muted">授权国际站店铺后，可在这里管理默认设置并批量上品。</p>
      </div>
      <div class="head-actions">
        <el-button type="primary" @click="openEmbeddedOAuth">
          新增店铺
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="oauthError"
      type="error"
      show-icon
      title="店铺授权未完成"
      :description="oauthError"
      style="margin-bottom: 14px"
      @close="oauthError = ''"
    />

    <el-empty v-if="!store.shops.length && !loading" description="还没有店铺">
      <el-button type="primary" @click="openEmbeddedOAuth">
        新增店铺
      </el-button>
    </el-empty>

    <el-table v-if="store.shops.length" :data="store.shops" v-loading="loading">
      <el-table-column label="店铺" min-width="220">
        <template #default="{ row }">
          <div class="record">
            <span class="record-mark">{{ (row.name || "店").slice(0, 1) }}</span>
            <div>
              <div>{{ row.name }}</div>
              <div class="muted">{{ row.account || row.seller_id || "已授权" }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <span v-if="row.status === 'active' && row.connected" class="status-pill green">可用</span>
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
      <el-table-column label="操作" width="260" align="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="edit(row)">店铺默认</el-button>
          <el-button text type="primary" @click="use(row)">设为当前</el-button>
          <el-button v-if="row.status !== 'active'" text type="primary" @click="openEmbeddedOAuth">
            重新授权
          </el-button>
          <el-button text type="danger" @click="unbind(row)">解绑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="oauthOpen"
      title="新增店铺"
      width="min(920px, 96vw)"
      destroy-on-close
      @closed="closeOAuthDialog"
    >
      <p class="muted" style="margin: 0 0 12px">
        在阿里官方页面确认授权，把发品相关能力授权给我们。若内嵌页空白，请点「弹窗授权」。
      </p>
      <div class="oauth-toolbar">
        <el-button :loading="oauthLoading" @click="reloadOAuthFrame">刷新授权页</el-button>
        <el-button type="primary" @click="openOAuthPopup">弹窗授权</el-button>
      </div>
      <iframe v-if="oauthUrl" ref="oauthFrame" :src="oauthUrl" class="oauth-frame" title="阿里官方授权" />
    </el-dialog>

    <el-drawer v-model="drawer" size="460px" :title="`${editing?.name || ''} · 店铺默认`">
      <p class="muted" style="margin-bottom: 16px">
        官方不是整店填一套就套所有货。店里定产地、付款、样品；包装、单位、运费、交期跟每条货走，成稿时先用这类目自己的习惯，没有才用下面的兜底。
      </p>
      <p v-if="optionSource.pulled?.length" class="muted" style="margin: -8px 0 16px">
        刚从在线商品补上：{{ pulledLabels }}。你随时可以改，改过的以后不会被再覆盖。
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

        <p class="section-label">整店通用</p>
        <p class="muted" style="margin: -4px 0 12px">
          官方也是店里设好这些，发品时每条引用。选项来自{{ optionSource.category_name || "这家店的发布规则" }}。
        </p>
        <el-form-item v-for="field in shopFields" :key="field.key" :label="field.label">
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

        <p class="section-label">跟货走的兜底</p>
        <p class="muted" style="margin: -4px 0 12px">
          官方批量改包装、单位、运费、交期是一条一条改的。这里只在这类目还没有自己的习惯时用。某类货不一样，去「类目模板」或草稿里改那一类。
        </p>
        <el-form-item v-for="field in productFields" :key="field.key" :label="field.label">
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
        <el-form-item label="常用包装">
          <div style="display: flex; gap: 8px">
            <el-input v-model="editing.defaults.pkgLength" placeholder="长 cm" />
            <el-input v-model="editing.defaults.pkgWidth" placeholder="宽 cm" />
            <el-input v-model="editing.defaults.pkgHeight" placeholder="高 cm" />
          </div>
        </el-form-item>
        <el-form-item label="常用重量">
          <el-input v-model="editing.defaults.pkgWeight" placeholder="kg" />
        </el-form-item>
        <el-form-item label="常用交期">
          <el-input v-model="editing.defaults.ladderPeriod" placeholder="15" />
          <div class="muted" style="margin-top: 6px">天数。交期必须是你定的，AI 不准编。单条货不一样就在草稿改。</div>
        </el-form-item>
        <el-form-item label="整店品牌">
          <el-input v-model="editing.defaults.brand" placeholder="没有就留空" />
        </el-form-item>

        <p v-if="unsupported.length" class="muted" style="margin: 0 0 14px">
          这个店的类目没有{{ unsupported.map((item) => item.label).join("、") }}，官方规则里就没有这些字段，不用填。
        </p>
        <div style="display: flex; gap: 8px; flex-wrap: wrap">
          <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          <el-button :loading="optionsLoading" @click="reloadFromShop">重新从店里拉</el-button>
        </div>
      </el-form>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const saving = ref(false);
const drawer = ref(false);
const editing = ref(null);
const oauthError = ref("");
const optionsLoading = ref(false);
const optionSource = ref({ category_name: "", fields: [] });
const pickedLabels = ref({});
const oauthAvailable = ref(false);
const oauthOpen = ref(false);
const oauthUrl = ref("");
const oauthLoading = ref(false);
const oauthPopup = ref(null);

const pickable = computed(() => (optionSource.value.fields || []).filter((item) => item.kind === "select"));
const shopFields = computed(() => pickable.value.filter((item) => item.scope !== "product"));
const productFields = computed(() => pickable.value.filter((item) => item.scope === "product"));
const unsupported = computed(() => (optionSource.value.fields || []).filter((item) => item.kind === "unsupported"));
const pulledLabels = computed(() => {
  const names = { origin: "产地", priceUnit: "单位", saleType: "售卖方式", shippingTemplateId: "运费模板", logisticsProperty: "物流属性", marketSample: "样品", paymentMethod: "付款", port: "港口", market: "市场", pkgWeight: "包装重量", pkgLength: "包装长", pkgWidth: "包装宽", pkgHeight: "包装高", brand: "品牌", ladderPeriod: "交期" };
  return (optionSource.value.pulled || []).map((key) => names[key] || key).join("、");
});

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

async function loadConnectOptions() {
  try {
    const options = await api.shopConnectOptions();
    oauthAvailable.value = Boolean(options.oauth_available);
    return;
  } catch {
    // Older servers may not expose connect-options yet; health still tells us
    // whether the platform OAuth app is configured.
  }
  try {
    const health = await api.health();
    oauthAvailable.value = Boolean(health.platform_ready);
  } catch {
    oauthAvailable.value = true;
  }
}

async function loadOptions(shopId, refresh = false) {
  optionsLoading.value = true;
  try {
    optionSource.value = await api.shopDefaultOptions(shopId, "", { refresh });
    if (!editing.value.defaults) editing.value.defaults = {};
    for (const field of optionSource.value.fields || []) {
      if (field.kind === "unsupported") continue;
      editing.value.defaults[field.key] = field.multiple ? splitValues(field.value) : field.value;
      if (field.kind === "select") rememberLabel(field);
    }
    if (refresh && optionSource.value.pulled?.length) {
      ElMessage.success(`已从店里更新：${pulledLabels.value}`);
    }
    await store.loadShops();
  } catch (error) {
    optionSource.value = { category_name: "", fields: [], pulled: [] };
    ElMessage.warning(`拉不到官方选项，先手填：${error.message}`);
  } finally {
    optionsLoading.value = false;
  }
}

function reloadFromShop() {
  if (!editing.value?.id) return;
  loadOptions(editing.value.id, true);
}

if (route.query.alibaba === "error") {
  oauthError.value = route.query.message || "阿里没有确认成功。请再试一次授权。";
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

async function finishOAuthSuccess() {
  oauthOpen.value = false;
  oauthError.value = "";
  await reload();
  ElMessage.success("店铺已授权");
}

function onOAuthMessage(event) {
  if (event.origin !== window.location.origin) return;
  const payload = event.data;
  if (!payload || payload.type !== "alibaba-oauth") return;
  if (payload.status === "connected") {
    finishOAuthSuccess();
    return;
  }
  oauthOpen.value = false;
  oauthError.value = payload.message || "阿里没有确认成功";
}

async function loadOAuthUrl() {
  oauthLoading.value = true;
  try {
    const data = await api.oauthStart(true);
    oauthUrl.value = data.url;
  } catch (error) {
    oauthError.value = error.message;
    oauthOpen.value = false;
  } finally {
    oauthLoading.value = false;
  }
}

async function openEmbeddedOAuth() {
  if (!oauthAvailable.value) {
    ElMessage.warning("平台还没有接好国际站应用，暂时不能授权店铺");
    return;
  }
  oauthOpen.value = true;
  await loadOAuthUrl();
}

function reloadOAuthFrame() {
  loadOAuthUrl();
}

function openOAuthPopup() {
  if (!oauthUrl.value) return;
  if (oauthPopup.value && !oauthPopup.value.closed) {
    oauthPopup.value.focus();
    return;
  }
  const width = 520;
  const height = 720;
  const left = window.screenX + Math.max(0, (window.outerWidth - width) / 2);
  const top = window.screenY + Math.max(0, (window.outerHeight - height) / 2);
  oauthPopup.value = window.open(
    oauthUrl.value,
    "alibaba-oauth",
    `width=${width},height=${height},left=${left},top=${top},noopener,noreferrer`,
  );
}

function closeOAuthDialog() {
  oauthUrl.value = "";
  if (oauthPopup.value && !oauthPopup.value.closed) oauthPopup.value.close();
  oauthPopup.value = null;
}

onMounted(async () => {
  window.addEventListener("message", onOAuthMessage);
  await loadConnectOptions();
  await reload();
  if (route.query.alibaba === "connected") {
    await finishOAuthSuccess();
    router.replace({ path: "/shops" });
  }
});

onUnmounted(() => {
  window.removeEventListener("message", onOAuthMessage);
  closeOAuthDialog();
});

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

<style scoped>
.head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.section-label {
  margin: 18px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}
.oauth-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.oauth-frame {
  width: 100%;
  height: min(68vh, 640px);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #fff;
}
</style>
