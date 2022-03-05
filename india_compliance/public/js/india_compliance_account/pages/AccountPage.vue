<template>
  <h1>Welcome to Account Page</h1>
</template>

<script>
export default {
  beforeRouteEnter(to, from, next) {
    next((vm) => {
      vm.$store.getters.isLoggedIn ? next() : next({ name: "auth" });
    });
  },
};
</script>