<template>
  <div class="loading-container">
    <h1>India Compliance</h1>
    <h5>by Resilient Tech</h5>
    <Loading :radius="40" class="mt-3" />
  </div>
</template>

<script>
import Loading from "./Loading.vue";

export default {
  components: { Loading },
};
</script>

<style scoped>
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  flex-direction: column;
  height: calc(100vh - 60px);
}
</style>