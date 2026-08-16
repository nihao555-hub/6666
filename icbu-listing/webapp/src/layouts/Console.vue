<template>
  <div class="console">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <Brand />
      </div>

      <div class="shop-switcher">
        <el-select
          v-model="shopId"
          placeholder="先授权店铺"
          :no-data-text="'还没有店铺'"
          @change="onShopChange"
        >
          <el-option v-for="shop in store.shops" :key="shop.id" :label="shop.name" :value="shop.id" />
        </el-select>
      </div>

      <nav class="nav-list">
        <router-link class="nav-link" :class="{ 'is-active': on('/overview') }" to="/overview">
          <svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
          概览
        </router-link>
        <router-link class="nav-link" :class="{ 'is-active': on('/shops') }" to="/shops">
          <svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M3 10.5 12 4l9 6.5" />
            <path d="M5 10v9h14v-9" />
          </svg>
          店铺
        </router-link>
        <router-link class="nav-link" :class="{ 'is-active': on('/feed') }" to="/feed">
          <svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M12 5v14M5 12h14" />
          </svg>
          投料
        </router-link>
        <router-link class="nav-link" :class="{ 'is-active': on('/drafts') }" to="/drafts">
          <svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M7 3h7l5 5v13H7z" />
            <path d="M14 3v5h5" />
          </svg>
          草稿箱
        </router-link>
        <router-link class="nav-link" :class="{ 'is-active': on('/queue') }" to="/queue">
          <svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M4 12a8 8 0 1 0 2.3-5.7" />
            <path d="M4 4v4h4" />
          </svg>
          队列
        </router-link>
      </nav>

      <div class="sidebar-foot">
        <div class="sidebar-user">
          <span class="avatar">{{ initials }}</span>
          <span>{{ store.user?.email }}</span>
        </div>
        <el-button text @click="logout">退出</el-button>
      </div>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <div class="topbar-title">{{ pageTitle }}</div>
        <div class="topbar-right">
          <el-tag v-if="store.shop && store.shop.status !== 'active'" type="danger" size="small">授权异常</el-tag>
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
import Brand from "../components/Brand.vue";
import { api } from "../api";
import { store } from "../store";

const TITLES = {
  overview: "概览",
  shops: "店铺",
  feed: "投料",
  drafts: "草稿箱",
  queue: "队列",
  products: "商品库",
  templates: "类目模板",
  online: "在线商品",
};

const route = useRoute();
const router = useRouter();
const shopId = ref(store.shopId);
const pageTitle = computed(() => {
  if (route.path.startsWith("/drafts/")) return "审稿";
  return TITLES[route.path.split("/")[1]] || "概览";
});
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
