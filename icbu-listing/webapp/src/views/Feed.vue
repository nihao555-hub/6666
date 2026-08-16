<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>投料上品</h2>
        <p class="muted">
          你只提供机器推不出来的东西：图、价格、起订量。类目、属性、英文标题、关键词、详情由 AI 按官方规则生成。
          投料会同时写入「商品库」——多店时不用重新丢图，去商品库勾店铺铺货即可。
        </p>
      </div>
    </div>

    <el-alert
      v-if="!store.shopId"
      type="warning"
      show-icon
      :closable="false"
      title="先绑一个店铺"
      description="投料需要用店铺的授权去拿类目规则和上传图片银行。"
      style="margin-bottom: 14px"
    />

    <el-tabs v-model="tab">
      <el-tab-pane label="单条上品" name="single">
        <div class="card">
          <el-form label-width="96px" style="max-width: 620px">
            <el-form-item label="产品图">
              <el-upload
                v-model:file-list="files"
                list-type="picture-card"
                :auto-upload="false"
                :limit="6"
                accept="image/*"
              >
                <span style="font-size: 22px">+</span>
              </el-upload>
              <div class="muted">1～6 张。第一张作主图，会先进图片银行再发布。</div>
            </el-form-item>
            <el-form-item label="货号">
              <el-input v-model="form.sku" placeholder="留空则用图片文件名" />
            </el-form-item>
            <el-form-item label="单价">
              <el-input v-model="form.price" placeholder="12.50">
                <template #append>USD</template>
              </el-input>
            </el-form-item>
            <el-form-item label="起订量">
              <el-input v-model="form.moq" placeholder="100" />
            </el-form-item>
            <el-form-item label="补充说明">
              <el-input
                v-model="form.note"
                type="textarea"
                :rows="2"
                placeholder="可选。中文也行，例如：加厚款，可定制 logo"
              />
            </el-form-item>
            <el-button type="primary" :loading="loading" :disabled="!store.shopId" @click="submitOne">
              生成草稿
            </el-button>
            <span v-if="loading" class="muted" style="margin-left: 12px">
              正在看图、定类目、拉规则、写文案，大约 20～40 秒
            </span>
          </el-form>
        </div>
      </el-tab-pane>

      <el-tab-pane label="批量上品" name="batch">
        <div class="card">
          <p class="muted" style="margin-bottom: 14px">
            按工厂习惯来：图片名以货号开头，<code>SKU-1001_1.jpg</code> 和 <code>SKU-1001_2.jpg</code>
            会自动归成同一个商品，并写入商品库。价格和起订量整批统一，进草稿箱后可以逐条改。
          </p>
          <el-form label-width="96px" style="max-width: 620px">
            <el-form-item label="图片">
              <el-upload
                v-model:file-list="batchFiles"
                :auto-upload="false"
                multiple
                accept="image/*"
                drag
                style="width: 100%"
              >
                <div style="padding: 26px 0">把整个文件夹的图拖进来</div>
              </el-upload>
            </el-form-item>
            <el-form-item label="统一单价">
              <el-input v-model="form.price" placeholder="12.50" />
            </el-form-item>
            <el-form-item label="统一起订量">
              <el-input v-model="form.moq" placeholder="100" />
            </el-form-item>
            <el-button type="primary" :loading="loading" :disabled="!store.shopId" @click="submitBatch">
              开始批量成稿
            </el-button>
          </el-form>

          <el-divider v-if="batch" />
          <div v-if="batch">
            <p>
              批次 {{ batch.batch_id.slice(0, 8) }}：共 {{ batch.count }} 个商品，已完成
              {{ progress.done }} 个。可以直接去草稿箱，任务在后台继续跑。
            </p>
            <el-progress :percentage="percent" :stroke-width="14" />
            <el-button style="margin-top: 12px" @click="$router.push('/drafts')">去草稿箱</el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onUnmounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const router = useRouter();
const tab = ref("single");
const loading = ref(false);
const files = ref([]);
const batchFiles = ref([]);
const batch = ref(null);
const progress = ref({ done: 0 });
const form = reactive({ sku: "", price: "", moq: "", note: "" });
let timer = null;

const percent = computed(() => {
  if (!batch.value?.count) return 0;
  return Math.min(100, Math.round((progress.value.done / batch.value.count) * 100));
});

onUnmounted(() => clearInterval(timer));

async function submitOne() {
  if (!files.value.length) {
    ElMessage.warning("至少传一张图");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("sku", form.sku);
  body.append("price", form.price);
  body.append("moq", form.moq);
  body.append("note", form.note);
  files.value.forEach((item) => item.raw && body.append("files", item.raw));

  loading.value = true;
  try {
    const draft = await api.feed(body);
    ElMessage.success(`草稿已生成：${draft.category_name || "待定类目"}`);
    router.push(`/drafts/${draft.id}`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function submitBatch() {
  if (!batchFiles.value.length) {
    ElMessage.warning("先把图片拖进来");
    return;
  }
  const body = new FormData();
  body.append("shop_id", store.shopId);
  body.append("price", form.price);
  body.append("moq", form.moq);
  batchFiles.value.forEach((item) => item.raw && body.append("files", item.raw));

  loading.value = true;
  try {
    batch.value = await api.feedBatch(body);
    progress.value = { done: 0 };
    clearInterval(timer);
    timer = setInterval(poll, 3000);
    ElMessage.success(`已拆成 ${batch.value.count} 个商品，正在后台成稿`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function poll() {
  if (!batch.value) return;
  try {
    progress.value = await api.batchProgress(batch.value.batch_id);
    if (progress.value.done >= batch.value.count) clearInterval(timer);
  } catch {
    clearInterval(timer);
  }
}
</script>
