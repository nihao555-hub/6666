<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>概览</h2>
        <p class="muted">上品在投料，看状态和改每个品在商品，发布进度在队列。</p>
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
      title="还不能连国际站"
      description="管理员还没有接好平台应用。先去店铺页看能不能登录。"
      style="margin-bottom: 14px"
    />
    <el-alert
      v-if="data.ai_enabled === false"
      type="warning"
      show-icon
      :closable="false"
      title="自动成稿暂时关着"
      description="类目、属性和标题需要你自己核对。接上模型之后会自动填。"
      style="margin-bottom: 14px"
    />

    <div class="hero" v-if="data.situation">
      <div class="hero-main">
        <div class="hero-kicker">今天先做这一步</div>
        <h3>{{ data.situation.title }}</h3>
        <p class="muted">{{ data.situation.why }}</p>
        <div class="chips" v-if="data.situation.ai_does?.length">
          <span class="chip" v-for="item in data.situation.ai_does" :key="item">{{ item }}</span>
        </div>
        <el-button type="primary" @click="$router.push(data.situation.action.to)">
          {{ data.situation.action.label }}
        </el-button>
        <div class="alt-list" v-if="extraPaths.length" style="margin-top: 16px; margin-bottom: 0">
          <p class="muted" style="margin-bottom: 6px">也可以走这些</p>
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
      <img class="hero-art" src="/art/hero.png" alt="" />
    </div>

    <div class="map-grid">
      <button class="map-card" @click="$router.push('/feed')">
        <small>上品</small>
        <b>投料</b>
        <span class="muted">有图就丢图，没图平台生成套图。再填价和起订量。</span>
      </button>
      <button class="map-card" @click="$router.push('/drafts')">
        <small>看状态 · 改每个品</small>
        <b>商品</b>
        <span class="muted">点进去改标题、价格、起订量，保存立刻生效。</span>
      </button>
      <button class="map-card" @click="$router.push('/queue')">
        <small>发布进度</small>
        <b>队列</b>
        <span class="muted">发到店里成功还是失败，失败改完重发。</span>
      </button>
    </div>

    <div class="stat-grid">
      <div class="stat">
        <span class="muted">已登录店铺</span>
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

<style scoped>
.map-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 16px;
}
.map-card {
  text-align: left;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: var(--radius);
  padding: 12px 14px;
  cursor: pointer;
  font-family: inherit;
  color: inherit;
}
.map-card:hover {
  background: var(--gray2);
}
.map-card small {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  margin-bottom: 4px;
}
.map-card b {
  display: block;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 4px;
}
@media (max-width: 900px) {
  .map-grid {
    grid-template-columns: 1fr;
  }
}
</style>
