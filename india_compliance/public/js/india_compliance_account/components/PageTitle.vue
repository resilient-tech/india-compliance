<template>
  <h2 class="page-heading">
    {{ title }}
  </h2>
</template>

<script>
export default {
  props: ["title"],
};
</script>

<style scoped>
.page-heading {
  margin-top: 1.7em;
  font-size: 2em;
  text-align: left;
  margin-bottom: 2em;
}

.full-stop-highlight {
  color: var(--primary-color);
  font-size: 1.2em;
}
</style>
