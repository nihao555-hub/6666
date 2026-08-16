<template>
  <div class="page">
    <div class="page-head">
      <div>
        <p class="page-kicker">工作台</p>
        <h2>今天先做这一步</h2>
        <p class="muted">按你现在的店铺处境推荐最快路径。绿项系统直接采用，不打断你。</p>
      </div>
      <el-button type="primary" @click="$router.push(data.situation?.action?.to || '/feed')">
        {{ data.situation?.action?.label || "去投料" }}
      </el-button>
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

    <div class="hero">
      <div class="hero-main" v-if="data.situation">
        <div class="hero-kicker">推荐路径</div>
        <h3>{{ data.situation.title }}</h3>
        <p class="muted">{{ data.situation.why }}</p>
        <p v-if="data.situation.official_note" class="muted" style="margin-top: 8px">
          对照官方：{{ data.situation.official_note }}
        </p>
        <div class="chips" v-if="data.situation.ai_does?.length">
          <span class="chip" v-for="item in data.situation.ai_does" :key="item">{{ item }}</span>
        </div>
        <el-button type="primary" @click="$router.push(data.situation.action.to)">
          {{ data.situation.action.label }}
        </el-button>
      </div>
      <div class="card">
        <h3>换一条路</h3>
        <p class="muted" style="margin-bottom: 12px">起点不一样就换，都是为了少填。</p>
        <div class="alt-grid">
          <button
            v-for="item in data.situation?.alternatives || []"
            :key="item.id"
            class="alt-btn"
            @click="$router.push(item.to)"
          >
            <b>{{ item.label }}</b>
            <span>{{ item.hint }}</span>
          </button>
        </div>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat">
        <span class="muted">已授权店铺</span>
        <b>{{ data.shops ?? 0 }}</b>
      </div>
      <div class="stat">
        <span class="muted">商品库</span>
        <b>{{ data.products ?? 0 }}</b>
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
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";

const data = ref({});

onMounted(async () => {
  try {
    data.value = await api.overview();
  } catch (error) {
    ElMessage.error(error.message);
  }
});
</script>
