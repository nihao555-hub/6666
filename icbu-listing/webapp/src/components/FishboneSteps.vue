<template>
  <div class="fishbone">
    <button
      v-for="(step, index) in steps"
      :key="step.key"
      class="fishbone-step"
      :class="{ 'is-current': index === modelValue, 'is-done': index < reached && index !== modelValue }"
      :disabled="index > reached"
      @click="go(index)"
    >
      <b>{{ step.label }}</b>
    </button>
  </div>
</template>

<script setup>
const props = defineProps({
  steps: { type: Array, required: true },
  modelValue: { type: Number, default: 0 },
  // Highest step the seller has unlocked. Later steps stay inert rather than
  // hidden, so the whole path is visible from the first screen.
  reached: { type: Number, default: 0 },
});
const emit = defineEmits(["update:modelValue"]);

function go(index) {
  if (index <= props.reached) emit("update:modelValue", index);
}
</script>
