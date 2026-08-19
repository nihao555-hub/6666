<template>
  <div class="auth">
    <section class="auth-visual" aria-hidden="true">
      <img class="auth-photo" src="/art/login-hero.png" alt="" />
    </section>
    <section class="auth-panel">
      <div class="auth-card">
        <h2>{{ mode === "login" ? "欢迎回来" : "用注册码开通" }}</h2>
        <p class="muted">先开工作台账号。店铺要在里面用你自己的卖家账号再登录一次。</p>
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
        <p class="muted auth-note">店铺密码只在阿里官方页输入，这里不收集</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
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
  grid-template-columns: minmax(320px, 1.15fr) minmax(360px, 0.85fr);
  background: var(--shell);
}

.auth-visual {
  position: relative;
  overflow: hidden;
  min-height: 100%;
}

.auth-photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.auth-visual::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(20, 32, 68, 0.08), rgba(20, 32, 68, 0.22));
}

.auth-panel {
  display: grid;
  place-items: center;
  padding: 40px 28px;
  background: var(--surface);
}

.auth-card {
  width: min(400px, 100%);
}

.auth-card h2 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.auth-card :deep(.el-form) {
  margin-top: 22px;
}

.auth-card :deep(.el-input__wrapper),
.auth-card :deep(.el-textarea__inner) {
  background: var(--alpha-lighter) !important;
}

.auth-note {
  margin-top: 28px;
  text-align: center;
}

@media (max-width: 900px) {
  .auth {
    grid-template-columns: 1fr;
  }
  .auth-visual {
    min-height: 240px;
  }
}
</style>
