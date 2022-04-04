<template>
  <transition name="fade">
    <div class="form-message" v-if="!hideMessage" :class="color">
      <span v-html="message" />
      <span class="close" @click="dismiss">&times;</span>
    </div>
  </transition>
</template>

<script>
export default {
  props: ["message", "color"],
  emits: ["dismiss"],
  data() {
    return {
      hideMessage: false,
    };
  },
  methods: {
    dismiss() {
      this.hideMessage = true;
      this.$emit("dismiss");
    },
  },
};
</script>

<style scoped>
.close {
  cursor: pointer;
}
</style>