<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>类目模板</h2>
        <p class="muted">少数类目要单独固化字段时才用。日常在店铺里填一次默认值即可。</p>
      </div>
      <el-button type="primary" :disabled="!store.shopId" @click="openNew">新建模板</el-button>
    </div>

    <div class="advanced-note">这页不在日常导航里。店铺默认值已经覆盖大多数字段。</div>
    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column prop="category_id" label="类目 ID" width="140" />
      <el-table-column label="固化字段" min-width="280">
        <template #default="{ row }">
          <span class="muted">{{ Object.keys(row.values || {}).join("、") || "还没有字段" }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="edit(row)">编辑</el-button>
          <el-button text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>
        <div class="empty">这个店还没有模板。成稿时会自动套匹配类目的模板。</div>
      </template>
    </el-table>

    <el-drawer v-model="drawer" :title="form.id ? '编辑模板' : '新建模板'" size="460px">
      <el-form label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="叶子类目 ID">
          <el-input v-model="form.category_id" placeholder="从草稿箱类目名后面抄，例如 21111112" />
          <div class="muted">必须是叶子类目。成稿后草稿上会带这个 ID，抄过来即可。</div>
        </el-form-item>
        <el-form-item label="产地"><el-input v-model="form.values.origin" /></el-form-item>
        <el-form-item label="计量单位"><el-input v-model="form.values.priceUnit" placeholder="Piece/Pieces" /></el-form-item>
        <el-form-item label="物流属性"><el-input v-model="form.values.logisticsProperty" placeholder="普货" /></el-form-item>
        <el-form-item label="样品">
          <el-select v-model="form.values.marketSample">
            <el-option label="不提供" value="Unavailable" />
            <el-option label="提供" value="Available (recommended)" />
          </el-select>
        </el-form-item>
        <el-form-item label="运费模板 ID"><el-input v-model="form.values.shippingTemplateId" /></el-form-item>
        <el-form-item label="包装重量"><el-input v-model="form.values.pkgWeight" /></el-form-item>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </el-form>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const rows = ref([]);
const loading = ref(false);
const saving = ref(false);
const drawer = ref(false);
const form = reactive({
  id: "",
  name: "",
  category_id: "",
  values: { origin: "China", priceUnit: "Piece/Pieces", logisticsProperty: "普货", marketSample: "Unavailable" },
});

async function reload() {
  if (!store.shopId) {
    rows.value = [];
    return;
  }
  loading.value = true;
  try {
    rows.value = await api.templates({ shop_id: store.shopId });
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

onMounted(reload);
watch(() => store.shopId, reload);

function openNew() {
  form.id = "";
  form.name = "";
  form.category_id = "";
  form.values = { origin: "China", priceUnit: "Piece/Pieces", logisticsProperty: "普货", marketSample: "Unavailable" };
  drawer.value = true;
}

function edit(row) {
  form.id = row.id;
  form.name = row.name;
  form.category_id = row.category_id;
  form.values = { ...row.values };
  drawer.value = true;
}

async function save() {
  saving.value = true;
  const body = {
    shop_id: store.shopId,
    name: form.name,
    category_id: form.category_id,
    values: form.values,
  };
  try {
    if (form.id) await api.updateTemplate(form.id, body);
    else await api.createTemplate(body);
    drawer.value = false;
    await reload();
    ElMessage.success("已保存。之后这个类目的新草稿会自动套用空字段。");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function remove(row) {
  await api.deleteTemplate(row.id);
  await reload();
}
</script>
