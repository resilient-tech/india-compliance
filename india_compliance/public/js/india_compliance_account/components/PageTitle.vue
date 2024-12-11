<template>
  <h2 class="page-heading">
<<<<<<< HEAD
    {{ title }}<span class="full-stop-highlight">.</span>
=======
    {{ title }}
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
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
