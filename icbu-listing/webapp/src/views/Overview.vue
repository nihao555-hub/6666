<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>概览</h2>
        <p class="muted">入库一次 → 勾商品 × 勾店铺 → 只审红黄项 → 队列发布。绿项系统直接采用，不打断你。</p>
      </div>
      <el-button type="primary" @click="$router.push('/products')">去商品库</el-button>
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
      <el-steps :active="5" align-center style="margin-top: 18px">
        <el-step title="授权店铺" description="官方 OAuth，不交密码" />
        <el-step title="填一次默认" description="产地、单位、物流、样品" />
        <el-step title="入库 / 投料" description="图、Excel 或资料库" />
        <el-step title="铺到多店" description="勾商品 × 勾店铺" />
        <el-step title="审红黄项" description="绿项折叠不打断" />
        <el-step title="队列发布" description="失败可改再发" />
      </el-steps>
      <ol class="flow-list">
        <li>先在「店铺」里接入店铺，并填一次店铺默认值。</li>
        <li>「投料」丢图片，或用 Excel（领星资料库 / 店小秘按模板 / 马帮导出 / 智能探测）。系统会同时写入商品库。</li>
        <li>多店时到「商品库」勾商品 × 勾店铺，一键铺货。第二家店起会换标题角度，降低重铺风险。</li>
        <li>到「草稿」只处理红项和黄项。可按店铺筛，也可看全部店铺。</li>
        <li>勾选后点「入队刊登」，到「队列」看结果。</li>
      </ol>
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

<style scoped>
.flow-list {
  margin: 22px 0 0;
  padding-left: 20px;
  color: #606266;
  line-height: 1.8;
}
</style>
