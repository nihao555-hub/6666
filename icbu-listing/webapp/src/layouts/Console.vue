<template>
  <div class="console" :class="{ 'is-collapsed': store.sidebarCollapsed }">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <Brand />
        <button class="sidebar-toggle" type="button" :title="store.sidebarCollapsed ? '展开侧栏' : '收起侧栏'" @click="store.toggleSidebar()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <path v-if="store.sidebarCollapsed" d="M9 6l6 6-6 6" />
            <path v-else d="M15 6l-6 6 6 6" />
          </svg>
        </button>
      </div>

      <div class="shop-switcher">
        <el-select
          v-model="shopId"
          placeholder="先登录店铺"
          :no-data-text="'还没有店铺'"
          @change="onShopChange"
        >
          <el-option v-for="shop in store.shops" :key="shop.id" :label="shop.name" :value="shop.id" />
        </el-select>
      </div>

      <nav class="nav-list">
        <router-link class="nav-link" :class="{ 'is-active': on('/feed') }" to="/feed" title="投料">
          <svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M12 5v14M5 12h14" />
          </svg>
          <span class="nav-text">投料</span>
        </router-link>
        <router-link class="nav-link" :class="{ 'is-active': on('/drafts') }" to="/drafts" title="商品">
          <svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M7 3h7l5 5v13H7z" />
            <path d="M14 3v5h5" />
          </svg>
          <span class="nav-text">商品</span>
        </router-link>
        <router-link class="nav-link" :class="{ 'is-active': on('/shops') }" to="/shops" title="店铺">
          <svg class="nav-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M3 10.5 12 4l9 6.5" />
            <path d="M5 10v9h14v-9" />
          </svg>
          <span class="nav-text">店铺</span>
        </router-link>
      </nav>

      <div class="sidebar-foot">
        <div class="sidebar-user">
          <span class="avatar">{{ initials }}</span>
          <span class="nav-text">{{ store.user?.email }}</span>
        </div>
        <el-button class="nav-text" text @click="logout">退出</el-button>
      </div>
    </aside>

    <div class="workspace">
      <div v-if="store.shop && store.shop.status !== 'active'" class="auth-warn">当前店铺登录已失效，先去店铺页重新登录。</div>
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

const route = useRoute();
const router = useRouter();
const shopId = ref(store.shopId);
const initials = computed(() => (store.user?.email || "U").slice(0, 1).toUpperCase());

onMounted(async () => {
  try {
    if (!store.user) await store.loadUser();
    await store.ensureShops();
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
