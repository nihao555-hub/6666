<template>
  <div class="wrap">
    <div class="panel">
      <h1>Auto Shoper</h1>
      <p class="muted">
        阿里国际站 AI 批量上品。每个账号自己授权自己的店铺，可以绑多个店，店铺 token 互相隔离。
      </p>

      <el-form label-position="top" @submit.prevent>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="you@company.com" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" label="注册码">
          <el-input v-model="form.code" placeholder="向管理员索取" />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">
          {{ mode === "login" ? "登录" : "注册并进入" }}
        </el-button>
        <el-button text style="width: 100%; margin: 10px 0 0" @click="toggle">
          {{ mode === "login" ? "还没有账号？用注册码开通" : "已经有账号，去登录" }}
        </el-button>
      </el-form>
    </div>
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
.wrap {
  min-height: 100%;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #101f33 0%, #1b3557 100%);
}

.panel {
  width: 420px;
  background: #fff;
  border-radius: 12px;
  padding: 32px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.25);
}

h1 {
  margin: 0 0 8px;
  font-size: 22px;
}

.muted {
  margin: 0 0 20px;
  line-height: 1.6;
}
</style>
