<template>
  <el-container class="console">
    <el-aside width="216px" class="sidebar">
      <div class="brand">
        AUTO SHOPER
        <small>阿里国际站 · AI 批量上品</small>
      </div>
      <el-menu :default-active="active" router>
        <el-menu-item index="/overview">概览</el-menu-item>
        <el-menu-item index="/shops">店铺授权</el-menu-item>
        <el-menu-item index="/feed">投料上品</el-menu-item>
        <el-menu-item index="/drafts">草稿箱</el-menu-item>
        <el-menu-item index="/queue">发布队列</el-menu-item>
        <el-menu-item index="/online">在线商品</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header height="56px" class="topbar">
        <div class="topbar-left">
          <span class="muted">当前店铺</span>
          <el-select
            v-model="shopId"
            placeholder="还没有店铺"
            style="width: 240px"
            :no-data-text="'先去店铺授权绑定一个店'"
            @change="onShopChange"
          >
            <el-option v-for="shop in store.shops" :key="shop.id" :label="shop.name" :value="shop.id">
              <span>{{ shop.name }}</span>
              <el-tag v-if="shop.publish_mode === 'draft'" size="small" type="info" style="margin-left: 8px">草稿模式</el-tag>
            </el-option>
          </el-select>
          <el-tag v-if="store.shop && store.shop.status !== 'active'" type="danger" size="small">
            授权异常
          </el-tag>
        </div>
        <div class="topbar-left">
          <span class="muted">{{ store.user?.email }}</span>
          <el-button text @click="logout">退出</el-button>
        </div>
      </el-header>

      <el-main style="padding: 0">
        <router-view :key="store.shopId" />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const route = useRoute();
const router = useRouter();
const shopId = ref(store.shopId);
const active = computed(() => `/${route.path.split("/")[1] || "overview"}`);

onMounted(async () => {
  try {
    if (!store.user) await store.loadUser();
    await store.loadShops();
    shopId.value = store.shopId;
  } catch (error) {
    ElMessage.error(error.message);
  }
});

function onShopChange(value) {
  store.selectShop(value);
}

async function logout() {
  await api.logout();
  store.reset();
  router.push("/login");
}
</script>
