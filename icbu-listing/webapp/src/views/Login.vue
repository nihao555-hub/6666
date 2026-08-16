<template>
  <div class="auth">
    <section class="auth-brand">
      <div class="brand">
        <div class="brand-mark">A</div>
        <div class="brand-copy">
          <strong>AUTO SHOPER</strong>
          <small>国际站上品工作台</small>
        </div>
      </div>
      <h1>自己的店，自己的货。<br />人只审红黄项。</h1>
      <ul>
        <li>官方 OAuth 授权，不收集店铺密码</li>
        <li>图 + 价格 + 起订量，其余按 Schema 自动补</li>
        <li>多店隔离，商品库只识别一次</li>
      </ul>
    </section>
    <section class="auth-panel">
      <div class="auth-card">
        <p class="page-kicker">{{ mode === "login" ? "登录工作台" : "开通账号" }}</p>
        <h2>{{ mode === "login" ? "欢迎回来" : "用注册码开通" }}</h2>
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
  grid-template-columns: 1.1fr 0.9fr;
}
.auth-brand {
  background: #0b1220;
  color: #d7deea;
  padding: 48px 56px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.auth-brand h1 {
  margin: 36px 0 20px;
  color: #fff;
  font-size: 36px;
  line-height: 1.25;
  letter-spacing: -0.03em;
  font-weight: 650;
}
.auth-brand ul {
  margin: 0;
  padding-left: 18px;
  line-height: 2;
  color: #9aa8bd;
}
.auth-panel {
  display: grid;
  place-items: center;
  background: #f4f6f9;
}
.auth-card {
  width: 400px;
  background: #fff;
  border: 1px solid #e8ebf0;
  border-radius: 10px;
  padding: 28px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}
.auth-card h2 {
  margin: 0 0 18px;
  font-size: 22px;
}
@media (max-width: 900px) {
  .auth {
    grid-template-columns: 1fr;
  }
  .auth-brand {
    display: none;
  }
}
</style>
