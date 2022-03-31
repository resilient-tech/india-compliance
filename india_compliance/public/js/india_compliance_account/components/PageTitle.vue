<template>
  <h2 class="page-heading">
    {{ title }}<span class="full-stop-highlight">.</span>
  </h2>
</template>

<script>
export default {
  props: ["title"],
};
</script>

<style>
.page-heading {
  margin-top: 1.7em;
  font-size: 2em;
  text-align: left;
}

.full-stop-highlight {
  color: var(--primary-color);
  font-size: 1.2em;
}
</style>