<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>商品库</h2>
        <p class="muted">图只识别一次，再勾店铺铺出去。日常投料会自动入库，一般不用单独打开这页。</p>
      </div>
      <div>
        <el-button :disabled="!selected.length" type="primary" @click="openDistribute">
          铺到店铺（{{ selected.length }}）
        </el-button>
        <el-button @click="$router.push({ path: '/feed', query: { tab: 'excel' } })">Excel 入库</el-button>
        <el-button @click="adding = true">入库新商品</el-button>
      </div>
    </div>

    <div class="advanced-note">这页不在日常导航里。只有概览判断「货已在库、直接铺店」时才会带你过来。</div>
    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜货号或品名" clearable style="width: 240px" @change="reload" />
      <div class="spacer"></div>
      <el-button text @click="reload">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" row-key="id" @selection-change="onSelect">
      <el-table-column type="selection" width="44" />
      <el-table-column label="图" width="70">
        <template #default="{ row }">
          <img v-if="row.images?.[0]" :src="row.images[0].url" class="thumb" />
          <div v-else class="thumb"></div>
        </template>
      </el-table-column>
      <el-table-column prop="sku" label="货号" width="140" show-overflow-tooltip />
      <el-table-column label="品名 / 识别" min-width="260">
        <template #default="{ row }">
          <div>{{ row.name || "（识别中或未识别）" }}</div>
          <span class="muted">{{ row.understanding?.category_hint || "—" }}</span>
        </template>
      </el-table-column>
      <el-table-column label="价格 / 起订" width="140">
        <template #default="{ row }">{{ row.price || "—" }} / {{ row.moq || "—" }}</template>
      </el-table-column>
      <el-table-column label="已生成草稿" width="120">
        <template #default="{ row }">{{ row.draft_count }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="pickOne(row)">铺这个</el-button>
          <el-button text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty">
          <img class="empty-art" src="/art/empty-drafts.png" alt="" />
          <b>还没有商品</b>
          点「入库新商品」，或去投料页拖图。
        </div>
      </template>
    </el-table>

    <el-drawer v-model="adding" title="入库新商品" size="460px">
      <p class="muted" style="margin-bottom: 14px">
        只存资料，不立刻发品。AI 会看一次图。之后再勾店铺批量生成草稿。
      </p>
      <el-form label-width="80px">
        <el-form-item label="产品图">
          <el-upload v-model:file-list="files" list-type="picture-card" :auto-upload="false" :limit="6" accept="image/*">
            <span>+</span>
          </el-upload>
        </el-form-item>
        <el-form-item label="货号"><el-input v-model="form.sku" /></el-form-item>
        <el-form-item label="单价"><el-input v-model="form.price" /></el-form-item>
        <el-form-item label="起订量"><el-input v-model="form.moq" /></el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" placeholder="可选，中文也行" />
        </el-form-item>
        <el-button type="primary" :loading="saving" @click="create">入库</el-button>
      </el-form>
    </el-drawer>

    <el-dialog v-model="distributing" title="铺到哪些店铺" width="520px">
      <p class="muted" style="margin-bottom: 12px">
        {{ selected.length }} 个商品 × 选中的店铺。每个店会各自传到店铺图库、各自成稿。
        勾选「差异化文案」后，第二家店起会换一个卖点角度，降低重铺风险。
      </p>
      <el-checkbox-group v-model="shopIds">
        <div v-for="shop in store.shops" :key="shop.id" style="margin: 8px 0">
          <el-checkbox :value="shop.id">{{ shop.name }}</el-checkbox>
        </div>
      </el-checkbox-group>
      <el-checkbox v-model="differentiate" style="margin-top: 12px">多店差异化文案（推荐）</el-checkbox>
      <template #footer>
        <el-button @click="distributing = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!shopIds.length" @click="doDistribute">
          生成 {{ selected.length * shopIds.length }} 条草稿
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const router = useRouter();
const rows = ref([]);
const loading = ref(false);
const saving = ref(false);
const adding = ref(false);
const distributing = ref(false);
const selected = ref([]);
const shopIds = ref([]);
const differentiate = ref(true);
const keyword = ref("");
const files = ref([]);
const form = reactive({ sku: "", price: "", moq: "", note: "" });

async function reload() {
  loading.value = true;
  try {
    rows.value = await api.products({ keyword: keyword.value });
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

onMounted(reload);

function onSelect(items) {
  selected.value = items;
}

function pickOne(row) {
  selected.value = [row];
  openDistribute();
}

function openDistribute() {
  if (!selected.value.length) {
    ElMessage.warning("先勾选商品");
    return;
  }
  shopIds.value = store.shopId ? [store.shopId] : store.shops.map((item) => item.id);
  distributing.value = true;
}

async function create() {
  if (!files.value.length) {
    ElMessage.warning("至少传一张图");
    return;
  }
  const body = new FormData();
  body.append("sku", form.sku);
  body.append("price", form.price);
  body.append("moq", form.moq);
  body.append("note", form.note);
  files.value.forEach((item) => item.raw && body.append("files", item.raw));
  saving.value = true;
  try {
    await api.createProduct(body);
    adding.value = false;
    files.value = [];
    ElMessage.success("已入库，AI 看过图了");
    await reload();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function doDistribute() {
  saving.value = true;
  try {
    const result = await api.distribute({
      product_ids: selected.value.map((item) => item.id),
      shop_ids: shopIds.value,
      differentiate: differentiate.value,
    });
    distributing.value = false;
    ElMessage.success(`已排队 ${result.count} 条草稿，后台在成稿`);
    router.push({ path: "/drafts", query: { shop: "all" } });
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function remove(row) {
  await api.deleteProduct(row.id);
  await reload();
}
</script>
