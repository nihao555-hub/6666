<template>
  <div class="auth">
    <div class="auth-card">
      <Brand size="lg" />
      <h2>{{ mode === "login" ? "欢迎回来" : "用注册码开通" }}</h2>
      <p class="muted">自己的店，自己的货。人只审红黄项。</p>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="工作邮箱">
          <el-input v-model="form.email" size="large" placeholder="you@company.com" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" size="large" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" label="注册码">
          <el-input v-model="form.code" size="large" placeholder="向管理员索取" />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">
          {{ mode === "login" ? "进入工作台" : "注册并进入" }}
        </el-button>
        <el-button text style="width: 100%; margin-top: 8px" @click="toggle">
          {{ mode === "login" ? "还没有账号？用注册码开通" : "已经有账号，去登录" }}
        </el-button>
      </el-form>
      <p class="muted auth-note">官方 OAuth 授权，不收集店铺密码</p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import Brand from "../components/Brand.vue";
import { api } from "../api";
import { store } from "../store";

const router = useRouter();
const mode = ref("login");
const loading = ref(false);
const form = reactive({ email: "", password: "", code: "" });

function toggle() {
  mode.value = mode.value === "login" ? "register" : "login";
}

async function submit() {
  loading.value = true;
  try {
    store.user = mode.value === "login" ? await api.login(form) : await api.register(form);
    await store.loadShops();
    router.push(store.shops.length ? "/overview" : "/shops");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.auth {
  min-height: 100%;
  display: grid;
  place-items: center;
  background: #f3f3f2;
}

.auth-card {
  width: 360px;
}

.auth-card h2 {
  margin: 28px 0 6px;
  font-size: 26px;
  font-weight: 550;
  letter-spacing: -0.03em;
}

.auth-card :deep(.el-form) {
  margin-top: 22px;
}

.auth-note {
  margin-top: 28px;
  text-align: center;
}
</style>
