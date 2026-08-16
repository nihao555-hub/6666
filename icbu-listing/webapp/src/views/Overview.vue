<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>今天先做这一步</h2>
        <p class="muted">系统按你现在的店况只推一条路。绿项自动过，你只处理红黄项。</p>
      </div>
    </div>

    <el-alert
      v-if="data.platform_ready === false"
      type="error"
      show-icon
      :closable="false"
      title="平台还没有配置国际站应用"
      description="环境变量需要 ALIBABA_APP_KEY 和 ALIBABA_APP_SECRET。"
      style="margin-bottom: 14px"
    />
    <el-alert
      v-if="data.ai_enabled === false"
      type="warning"
      show-icon
      :closable="false"
      title="没有配置模型，AI 成稿会跳过"
      description="填 OPENAI_API_KEY 后才会自动出类目、属性和标题。"
      style="margin-bottom: 14px"
    />

    <div class="hero" v-if="data.situation">
      <div class="hero-main">
        <div class="hero-kicker">推荐路径</div>
        <h3>{{ data.situation.title }}</h3>
        <p class="muted">{{ data.situation.why }}</p>
        <div class="chips" v-if="data.situation.ai_does?.length">
          <span class="chip" v-for="item in data.situation.ai_does" :key="item">{{ item }}</span>
        </div>
        <el-button type="primary" @click="$router.push(data.situation.action.to)">
          {{ data.situation.action.label }}
        </el-button>
      </div>
      <div class="alt-list" v-if="extraPaths.length">
        <p class="muted" style="margin-bottom: 6px">你现在还有这些更快的起点</p>
        <button
          v-for="item in extraPaths"
          :key="item.id"
          class="alt-btn"
          @click="$router.push(item.to)"
        >
          <b>{{ item.label }}</b>
          <span>{{ item.hint }}</span>
        </button>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat">
        <span class="muted">已授权店铺</span>
        <b>{{ data.shops ?? 0 }}</b>
      </div>
      <div class="stat">
        <span class="muted">待处理红项</span>
        <b style="color: var(--red)">{{ data.red ?? 0 }}</b>
      </div>
      <div class="stat">
        <span class="muted">可直接发布</span>
        <b style="color: var(--green)">{{ data.ready ?? 0 }}</b>
      </div>
      <div class="stat">
        <span class="muted">发布成功</span>
        <b>{{ data.success ?? 0 }}</b>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";

const data = ref({});
const extraPaths = computed(() =>
  (data.value.situation?.alternatives || []).filter((item) => ["clone", "catalogue"].includes(item.id)),
);

onMounted(async () => {
  try {
    data.value = await api.overview();
  } catch (error) {
    ElMessage.error(error.message);
  }
});
</script>
