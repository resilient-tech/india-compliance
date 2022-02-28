<template>
  <div class="loading-wrapper" :style="loadingWrapperStyle">
    <div class="loading" :style="loadingStyle"></div>
  </div>
</template>

<script>
export default {
  props: {
    radius: { default: 20 },
    stroke: { default: 2 },
    color: { default: "var(--primary-color)" },
  },

  computed: {
    loadingWrapperStyle() {
      return {
        width: this.radius + "px",
        height: this.radius + "px",
      };
    },
    loadingStyle() {
      return {
        borderWidth: this.stroke + "px",
        borderColor: this.color,
        borderTopColor: "transparent",
      };
    },
  },
};
</script>

<style scoped>
@keyframes loading {
  0% {
    transform: translate(-50%, -50%) rotate(0deg);
  }
  100% {
    transform: translate(-50%, -50%) rotate(360deg);
  }
}

.loading-wrapper {
  position: relative;
}

.loading {
  position: absolute;
  top: 50%;
  left: 50%;
  border-style: solid;
  border-radius: 50%;
  animation: loading 1.3s linear infinite;
  height: 100%;
  width: 100%;
}
</style>