<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>概览</h2>
        <p class="muted">投料 → 只审红黄项 → 队列发布。绿项系统直接采用，不打断你。</p>
      </div>
      <el-button type="primary" @click="$router.push('/feed')">去上品</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat">
        <span class="muted">已授权店铺</span>
        <b>{{ data.shops ?? 0 }}</b>
      </div>
      <div class="stat">
        <span class="muted">待处理红项</span>
        <b style="color: #f56c6c">{{ data.red ?? 0 }}</b>
      </div>
      <div class="stat">
        <span class="muted">可直接发布</span>
        <b style="color: #67c23a">{{ data.ready ?? 0 }}</b>
      </div>
      <div class="stat">
        <span class="muted">发布成功</span>
        <b>{{ data.success ?? 0 }}</b>
      </div>
    </div>

    <el-alert
      v-if="data.platform_ready === false"
      type="error"
      show-icon
      :closable="false"
      title="平台还没有配置国际站应用"
      description="需要在环境变量里填 ALIBABA_APP_KEY 和 ALIBABA_APP_SECRET，否则店铺无法授权。"
      style="margin-bottom: 14px"
    />
    <el-alert
      v-if="data.ai_enabled === false"
      type="warning"
      show-icon
      :closable="false"
      title="没有配置模型，AI 成稿会跳过"
      description="填 OPENAI_API_KEY 后，投料才会自动出类目、属性、标题和详情。"
      style="margin-bottom: 14px"
    />

    <div class="card">
      <h3>这套系统怎么用</h3>
      <el-steps :active="4" align-center style="margin-top: 18px">
        <el-step title="授权店铺" description="官方 OAuth，不交密码" />
        <el-step title="填一次店铺默认" description="产地、单位、物流、样品" />
        <el-step title="投料" description="传图 + 价格 + 起订量" />
        <el-step title="审红黄项" description="绿项折叠不打断" />
        <el-step title="队列发布" description="失败可改再发" />
      </el-steps>
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
