<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>店铺</h2>
        <p class="muted">授权国际站店铺后，在这里管店铺政策；跟货走的字段去「发品习惯」。</p>
      </div>
      <div class="head-actions">
        <el-button type="primary" :loading="bindingEnv" @click="openEmbeddedOAuth">
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
      <el-button type="primary" :loading="bindingEnv" @click="openEmbeddedOAuth">
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
            整店政策：产地 {{ shown(row, "origin") || "—" }} · 样品 {{ shown(row, "marketSample") || "—" }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="320" align="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="edit(row)">店铺政策</el-button>
          <el-button text type="primary" @click="openHabits(row)">发品习惯</el-button>
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

    <el-drawer v-model="drawer" size="460px" :title="`${editing?.name || ''} · 店铺政策`">
      <p class="muted" style="margin-bottom: 12px">
        只填整店政策：产地、售卖方式、样品等。跟货走的单位、包装、运费请去「发品习惯」。
      </p>
      <p v-if="optionSource.category_name" class="muted" style="margin-bottom: 12px">
        选项以「{{ optionSource.category_name }}」为例；不同类目可能多出或缺少字段。
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

        <p class="section-label">整店政策</p>
        <p class="muted" style="margin: -4px 0 12px">
          发品时每条货都会引用。付款、港口等若在本类目不存在，不代表全店都没有。
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

        <p v-if="unsupported.length" class="muted" style="margin: 0 0 14px">
          参考类目「{{ optionSource.category_name || "—" }}」里没有{{ unsupported.map((item) => item.label).join("、") }}。
        </p>
        <div style="display: flex; gap: 8px; flex-wrap: wrap">
          <el-button type="primary" :loading="saving" @click="save">保存政策</el-button>
          <el-button @click="openHabits(editing)">去发品习惯</el-button>
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
const connectOptions = ref({ bind_env_available: false, oauth_available: false, prefer_env_token: false });
const bindingEnv = ref(false);
const oauthOpen = ref(false);
const oauthUrl = ref("");
const oauthLoading = ref(false);
const oauthPopup = ref(null);

const pickable = computed(() => (optionSource.value.fields || []).filter((item) => item.kind === "select"));
const shopFields = computed(() => pickable.value.filter((item) => item.scope !== "product"));
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

async function loadConnectOptions() {
  try {
    connectOptions.value = await api.shopConnectOptions();
  } catch {
    try {
      const health = await api.health();
      connectOptions.value = {
        bind_env_available: false,
        oauth_available: Boolean(health.platform_ready),
        prefer_env_token: false,
      };
    } catch {
      connectOptions.value = { bind_env_available: false, oauth_available: true, prefer_env_token: false };
    }
  }
}

async function bindEnvShop({ silent = false } = {}) {
  bindingEnv.value = true;
  try {
    const shop = await api.bindEnvShop("测试店铺");
    await store.loadShops();
    store.selectShop(shop.id);
    if (!silent) ElMessage.success("已接入环境 token 对应的测试店铺");
    return shop;
  } catch (error) {
    if (!silent) ElMessage.error(error.message);
    throw error;
  } finally {
    bindingEnv.value = false;
  }
}

async function loadOptions(shopId) {
  optionsLoading.value = true;
  try {
    optionSource.value = await api.shopDefaultOptions(shopId, "", { pull: false });
    if (!editing.value.defaults) editing.value.defaults = {};
    for (const field of optionSource.value.fields || []) {
      if (field.kind === "unsupported" || field.scope === "product") continue;
      editing.value.defaults[field.key] = field.multiple ? splitValues(field.value) : field.value;
      if (field.kind === "select") rememberLabel(field);
    }
    await store.loadShops();
  } catch (error) {
    optionSource.value = { category_name: "", fields: [], pulled: [] };
    ElMessage.warning(`拉不到官方选项，先手填：${error.message}`);
  } finally {
    optionsLoading.value = false;
  }
}

function openHabits(shop) {
  store.selectShop(shop.id);
  router.push({ path: "/habits" });
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
  if (connectOptions.value.prefer_env_token) {
    await bindEnvShop();
    return;
  }
  if (!connectOptions.value.oauth_available) {
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
  if (!store.shops.length && connectOptions.value.prefer_env_token) {
    try {
      await bindEnvShop({ silent: true });
    } catch {
      // Leave empty state; user can click 新增店铺 to retry.
    }
  }
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
