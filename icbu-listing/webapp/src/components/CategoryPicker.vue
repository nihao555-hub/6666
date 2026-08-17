<template>
  <el-dialog v-model="open" title="选择类目" width="640px" @open="openNode('0')">
    <p class="muted" style="margin-bottom: 10px">
      <span v-for="(node, index) in path" :key="node.category_id">
        <el-link type="primary" @click="openNode(node.category_id)">{{ node.name }}</el-link>
        <span v-if="index < path.length - 1"> / </span>
      </span>
      <el-link v-if="path.length" type="info" style="margin-left: 8px" @click="openNode('0')">回到顶层</el-link>
    </p>
    <el-table :data="children" height="360" @row-click="(row) => openNode(row.category_id)">
      <el-table-column label="类目" min-width="240">
        <template #default="{ row }">
          {{ row.label }}
          <span v-if="row.is_leaf" class="status-pill green" style="margin-left: 6px">可发布</span>
        </template>
      </el-table-column>
      <el-table-column width="110" align="right">
        <template #default="{ row }">
          <el-button v-if="row.is_leaf" text type="primary" @click.stop="pick(row)">选这个</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { store } from "../store";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue", "pick"]);

const open = ref(props.modelValue);
const children = ref([]);
const path = ref([]);

watch(
  () => props.modelValue,
  (value) => {
    open.value = value;
  },
);
watch(open, (value) => emit("update:modelValue", value));

async function openNode(parent) {
  if (!store.shopId) {
    ElMessage.warning("先登录一个店铺");
    return;
  }
  try {
    const data = await api.categories(store.shopId, parent);
    children.value = data.children || [];
    path.value = data.path || [];
  } catch (error) {
    ElMessage.error(error.message);
  }
}

function pick(row) {
  emit("pick", row);
  open.value = false;
}
</script>
