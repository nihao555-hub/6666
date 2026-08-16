<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>店铺</h2>
        <p class="muted">官方 OAuth 授权，只保存加密 token。每个店填一次默认值，后面不用再问。</p>
      </div>
      <div>
        <el-button v-if="showDevBind" @click="bindEnv">用环境 token 接入（本地调试）</el-button>
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
          <b>{{ row.name }}</b>
          <div class="muted">{{ row.account || row.seller_id || "—" }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'active' && row.connected" type="success" size="small">已授权</el-tag>
          <el-tag v-else-if="row.status === 'expired'" type="warning" size="small">需重新授权</el-tag>
          <el-tag v-else type="danger" size="small">异常</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="发布模式" width="130">
        <template #default="{ row }">
          <el-tag :type="row.publish_mode === 'online' ? 'danger' : 'info'" size="small">
            {{ row.publish_mode === "online" ? "直接上架" : "只发草稿" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="默认设置" min-width="280">
        <template #default="{ row }">
          <span class="muted">
            产地 {{ row.defaults.origin }} · 单位 {{ row.defaults.priceUnit }} · 物流 {{ row.defaults.logisticsProperty }}
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
        这些是经营决策，AI 不猜。填一次，之后每条商品自动套用，投料时就不用再问了。
      </p>
      <el-form v-if="editing" label-width="110px">
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
        <el-form-item label="产地">
          <el-input v-model="editing.defaults.origin" />
        </el-form-item>
        <el-form-item label="计量单位">
          <el-input v-model="editing.defaults.priceUnit" placeholder="Piece/Pieces" />
        </el-form-item>
        <el-form-item label="物流属性">
          <el-input v-model="editing.defaults.logisticsProperty" placeholder="普货" />
        </el-form-item>
        <el-form-item label="样品服务">
          <el-select v-model="editing.defaults.marketSample">
            <el-option label="不提供样品" value="Unavailable" />
            <el-option label="提供样品" value="Available (recommended)" />
          </el-select>
        </el-form-item>
        <el-form-item label="运费模板 ID">
          <el-input v-model="editing.defaults.shippingTemplateId" placeholder="留空则走买卖双方协商" />
        </el-form-item>
        <el-form-item label="包装重量">
          <el-input v-model="editing.defaults.pkgWeight" placeholder="kg" />
        </el-form-item>
        <el-form-item label="包装尺寸">
          <div style="display: flex; gap: 8px">
            <el-input v-model="editing.defaults.pkgLength" placeholder="长" />
            <el-input v-model="editing.defaults.pkgWidth" placeholder="宽" />
            <el-input v-model="editing.defaults.pkgHeight" placeholder="高" />
          </div>
        </el-form-item>
        <el-form-item label="品牌">
          <el-input v-model="editing.defaults.brand" placeholder="没有就留空" />
        </el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </el-form>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const route = useRoute();
const loading = ref(false);
const saving = ref(false);
const drawer = ref(false);
const editing = ref(null);
const showDevBind = ref(true);
const oauthError = ref("");

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
  drawer.value = true;
}

function use(shop) {
  store.selectShop(shop.id);
  ElMessage.success(`当前店铺切到「${shop.name}」`);
}

async function save() {
  saving.value = true;
  try {
    await api.saveDefaults(editing.value.id, {
      defaults: editing.value.defaults,
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
