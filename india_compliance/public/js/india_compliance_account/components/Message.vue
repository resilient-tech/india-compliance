<template>
  <div class="form-message" :class="color">{{ message }}</div>
</template>

<script>
export default {
  props: ["message", "color"],
};
</script>