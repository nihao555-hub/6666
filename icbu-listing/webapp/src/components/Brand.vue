<template>
  <div class="brand" :class="size">
    <div class="brand-mark" aria-hidden="true">A</div>
    <div class="brand-copy">
      <strong>Auto Shoper</strong>
      <small>国际站上品</small>
    </div>
  </div>
</template>

<script setup>
defineProps({
  size: { type: String, default: "md" },
});
</script>
