<template>
  <div class="brand" :class="[size, tone]">
    <img class="brand-mark" src="/art/logo.png" alt="" />
    <div class="brand-copy">
      <strong>Auto Shoper</strong>
      <small>国际站上品</small>
    </div>
  </div>
</template>

<script setup>
defineProps({
  size: { type: String, default: "md" },
  tone: { type: String, default: "dark" },
});
</script>
