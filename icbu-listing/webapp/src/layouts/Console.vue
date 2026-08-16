<template>
  <div class="console">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">A</div>
        <div class="brand-copy">
          <strong>AUTO SHOPER</strong>
          <small>国际站上品工作台</small>
        </div>
      </div>

      <div class="nav-group">工作台</div>
      <router-link class="nav-link" :class="{ 'is-active': on('/overview') }" to="/overview">
        <span class="nav-ico">▣</span>概览
      </router-link>
      <router-link class="nav-link" :class="{ 'is-active': on('/shops') }" to="/shops">
        <span class="nav-ico">⌂</span>店铺
      </router-link>

      <div class="nav-group">货盘</div>
      <router-link class="nav-link" :class="{ 'is-active': on('/feed') }" to="/feed">
        <span class="nav-ico">＋</span>投料
      </router-link>
      <router-link class="nav-link" :class="{ 'is-active': on('/products') }" to="/products">
        <span class="nav-ico">▤</span>商品库
      </router-link>
      <router-link class="nav-link" :class="{ 'is-active': on('/templates') }" to="/templates">
        <span class="nav-ico">☰</span>刊登模板
      </router-link>

      <div class="nav-group">发布</div>
      <router-link class="nav-link" :class="{ 'is-active': on('/drafts') }" to="/drafts">
        <span class="nav-ico">✎</span>草稿箱
      </router-link>
      <router-link class="nav-link" :class="{ 'is-active': on('/queue') }" to="/queue">
        <span class="nav-ico">↻</span>发布队列
      </router-link>
      <router-link class="nav-link" :class="{ 'is-active': on('/online') }" to="/online">
        <span class="nav-ico">◉</span>在线商品
      </router-link>

      <div class="sidebar-foot">只填图、价格、起订量<br />其余按官方 Schema 自动补</div>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <div class="topbar-left">
          <div class="crumb">工作台 / <b>{{ pageTitle }}</b></div>
          <el-select
            v-model="shopId"
            class="shop-switch"
            placeholder="选择店铺"
            :no-data-text="'先去店铺授权'"
            @change="onShopChange"
          >
            <el-option v-for="shop in store.shops" :key="shop.id" :label="shop.name" :value="shop.id">
              <span>{{ shop.name }}</span>
              <el-tag v-if="shop.publish_mode === 'draft'" size="small" type="info" style="margin-left: 8px">草稿</el-tag>
            </el-option>
          </el-select>
          <el-tag v-if="store.shop && store.shop.status !== 'active'" type="danger" size="small">授权异常</el-tag>
        </div>
        <div class="topbar-right">
          <div class="user-chip">
            <span class="avatar">{{ initials }}</span>
            <span>{{ store.user?.email }}</span>
          </div>
          <el-button text @click="logout">退出</el-button>
        </div>
      </header>
      <main class="workspace-main">
        <router-view :key="store.shopId" />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const TITLES = {
  overview: "概览",
  shops: "店铺",
  products: "商品库",
  feed: "投料",
  templates: "刊登模板",
  drafts: "草稿箱",
  queue: "发布队列",
  online: "在线商品",
};

const route = useRoute();
const router = useRouter();
const shopId = ref(store.shopId);
const pageTitle = computed(() => TITLES[route.path.split("/")[1]] || "概览");
const initials = computed(() => (store.user?.email || "U").slice(0, 1).toUpperCase());

onMounted(async () => {
  try {
    if (!store.user) await store.loadUser();
    await store.loadShops();
    shopId.value = store.shopId;
  } catch (error) {
    ElMessage.error(error.message);
  }
});

function on(path) {
  return route.path === path || route.path.startsWith(`${path}/`);
}

function onShopChange(value) {
  store.selectShop(value);
}

async function logout() {
  await api.logout();
  store.reset();
  router.push("/login");
}
</script>
