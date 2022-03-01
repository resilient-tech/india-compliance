<template>
  <div class="india-compliance-account">
    <AccountPage v-if="isAuthenticated" />
    <AuthPage v-else />
  </div>
</template>

<script>
import AccountPage from "./account/AccountPage.vue";
import AuthPage from "./auth/AuthPage.vue";

export default {
  components: {
    AuthPage,
    AccountPage,
  },

  computed: {
    isAuthenticated() {
      return false;
    },
  },
};
</script>