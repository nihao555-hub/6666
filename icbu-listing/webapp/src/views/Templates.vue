<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>类目模板</h2>
        <p class="muted">官方是按叶子类目发品的。画笔和家具包装、单位、运费可以不一样，在这里给这一类单独定习惯。</p>
      </div>
      <el-button type="primary" :disabled="!store.shopId" @click="openNew">新建模板</el-button>
    </div>

    <div class="advanced-note">这页不在日常导航里。整店政策在店铺默认里填；只有这一类货跟店里常用的不一样才建模板。</div>
    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column label="类目" min-width="220">
        <template #default="{ row }">{{ row.category_name || "类目待定" }}</template>
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
      <el-form v-loading="optionsLoading" label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类目">
          <el-button @click="browser = true">{{ form.category_name || "选择类目" }}</el-button>
        </el-form-item>
        <el-form-item v-for="field in pickable" :key="field.key" :label="field.label">
          <el-select v-model="form.values[field.key]" :multiple="field.multiple" filterable clearable style="width: 100%">
            <el-option v-for="option in field.options" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="包装重量"><el-input v-model="form.values.pkgWeight" /></el-form-item>
        <el-button type="primary" :loading="saving" :disabled="!form.category_id" @click="save">保存</el-button>
      </el-form>
    </el-drawer>
    <CategoryPicker v-model="browser" @pick="onCategory" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import CategoryPicker from "../components/CategoryPicker.vue";
import { api } from "../api";
import { store } from "../store";

const rows = ref([]);
const loading = ref(false);
const saving = ref(false);
const drawer = ref(false);
const browser = ref(false);
const optionsLoading = ref(false);
const optionFields = ref([]);
const form = reactive({
  id: "",
  name: "",
  category_id: "",
  category_name: "",
  values: {},
});

const pickable = computed(() => optionFields.value.filter((item) => item.kind === "select"));

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
  form.category_name = "";
  form.values = {};
  optionFields.value = [];
  drawer.value = true;
}

function edit(row) {
  form.id = row.id;
  form.name = row.name;
  form.category_id = row.category_id;
  form.category_name = row.category_name || row.name;
  form.values = { ...row.values };
  drawer.value = true;
  loadOptions(row.category_id);
}

async function onCategory(node) {
  form.category_id = node.category_id;
  form.category_name = node.label;
  if (!form.name) form.name = node.label;
  await loadOptions(node.category_id);
}

async function loadOptions(categoryId) {
  if (!store.shopId || !categoryId) return;
  optionsLoading.value = true;
  try {
    const data = await api.shopDefaultOptions(store.shopId, categoryId, { pull: false });
    optionFields.value = data.fields || [];
    for (const field of pickable.value) {
      if (form.values[field.key] == null || form.values[field.key] === "") {
        form.values[field.key] = field.value;
      }
    }
  } catch (error) {
    ElMessage.warning(error.message);
  } finally {
    optionsLoading.value = false;
  }
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
