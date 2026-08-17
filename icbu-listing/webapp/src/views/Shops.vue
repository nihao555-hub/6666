<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>店铺</h2>
        <p class="muted">用你自己的国际站卖家账号登录，授权本平台代你发品、改品、传图。</p>
      </div>
      <el-button type="primary" @click="authorize">{{ store.shops.length ? "登录自己的店铺" : "登录并授权店铺" }}</el-button>
    </div>

    <el-alert
      v-if="oauthError"
      type="error"
      show-icon
      title="店铺没有登录成功"
      :description="oauthError"
      style="margin-bottom: 14px"
      @close="oauthError = ''"
    />

    <el-alert
      v-if="hasTokenShop && !hasOauthShop"
      type="info"
      show-icon
      :closable="false"
      title="当前用已接入的店铺做完整上品测试"
      description="这家店对应环境里的授权。可以直接填默认、投料、审稿、发到官方草稿箱。"
      style="margin-bottom: 14px"
    />

    <div class="connect-card" v-if="!store.shops.length">
      <div class="connect-copy">
        <div class="hero-kicker">绑定自己的店</div>
        <h3>登录你的国际站店铺</h3>
        <p class="muted">
          会跳到阿里官方页。用你平时进卖家后台的账号确认即可。
          不收集店铺密码，只拿到发品、改品、传图需要的权限。
        </p>
        <ul class="connect-caps">
          <li>按你店里的类目规则成稿</li>
          <li>把产品图传到这家店</li>
          <li>发新品、改已有品</li>
          <li>看店里现在在售的货</li>
        </ul>
        <FishboneSteps v-model="connectStep" :steps="connectSteps" :reached="2" />
        <p class="muted" style="margin: 0 0 8px">开放平台里登记的回调地址必须和这一行完全一致，否则阿里会拒：</p>
        <div class="callback-row">
          <code>{{ callbackUrl }}</code>
          <el-button text type="primary" @click="copyCallback">复制</el-button>
        </div>
        <el-button type="primary" size="large" style="margin-top: 14px" @click="authorize">登录并授权店铺</el-button>
      </div>
      <img class="hero-art" src="/art/hero.png" alt="" />
    </div>

    <el-table v-if="store.shops.length" :data="store.shops" v-loading="loading">
      <el-table-column label="店铺" min-width="200">
        <template #default="{ row }">
          <div class="record">
            <span class="record-mark">{{ (row.name || "店").slice(0, 1) }}</span>
            <div>
              <div>{{ row.name }}</div>
              <div class="muted">{{ row.account || (row.bound_by === "debug" ? "已接入，可上品测试" : "已登录") }}</div>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <span v-if="row.status === 'active' && row.connected" class="status-pill green">{{ row.bound_by === "debug" ? "已接入" : "已登录" }}</span>
          <span v-else-if="row.status === 'expired'" class="status-pill yellow">需重新登录</span>
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
          <el-button v-if="row.status !== 'active'" text type="primary" @click="authorize">重新登录</el-button>
          <el-button text type="danger" @click="unbind(row)">解绑</el-button>
        </template>
      </el-table-column>
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
          选项来自这家店的官方发布规则（{{ optionSource.category_name }}），按官方选项选就行。
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
import FishboneSteps from "../components/FishboneSteps.vue";
import { api } from "../api";
import { store } from "../store";

const route = useRoute();
const loading = ref(false);
const saving = ref(false);
const drawer = ref(false);
const editing = ref(null);
const oauthError = ref("");
const optionsLoading = ref(false);
const optionSource = ref({ category_name: "", fields: [] });
const pickedLabels = ref({});
const connectStep = ref(0);
const connectSteps = [
  { key: "go", label: "跳转阿里" },
  { key: "login", label: "用你的账号登录" },
  { key: "back", label: "回来填默认" },
];

const pickable = computed(() => (optionSource.value.fields || []).filter((item) => item.kind === "select"));
const unsupported = computed(() => (optionSource.value.fields || []).filter((item) => item.kind === "unsupported"));
const hasTokenShop = computed(() => store.shops.some((item) => item.bound_by === "debug"));
const hasOauthShop = computed(() => store.shops.some((item) => item.bound_by === "oauth"));
const callbackUrl = `${window.location.origin}/api/v1/alibaba/oauth/callback`;

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
  oauthError.value = route.query.message || "阿里没有确认成功。请再点一次「登录并授权店铺」。";
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
    ElMessage.success("店铺已登录。先填一次默认值，之后每条商品不用再问。");
    edit(newest);
  }
});

async function copyCallback() {
  try {
    await navigator.clipboard.writeText(callbackUrl);
    ElMessage.success("已复制回调地址");
  } catch {
    ElMessage.error("复制失败，请手动选中");
  }
}

async function authorize() {
  try {
    const { url } = await api.oauthStart();
    window.location.href = url;
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

<style scoped>
.connect-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 232px;
  gap: 20px;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, var(--accent-wash), var(--surface) 70%);
  padding: 22px 24px;
}
.connect-copy h3 {
  margin: 6px 0 8px;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.02em;
}
.connect-caps {
  margin: 14px 0 18px;
  padding-left: 18px;
  color: var(--ink-2);
}
.connect-caps li + li {
  margin-top: 4px;
}
.callback-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: var(--gray3);
  border-radius: var(--radius);
}
.callback-row code {
  flex: 1;
  min-width: 0;
  overflow: auto;
  font-size: 12px;
  color: var(--ink-2);
}
@media (max-width: 900px) {
  .connect-card {
    grid-template-columns: 1fr;
  }
  .connect-card .hero-art {
    display: none;
  }
}
</style>
