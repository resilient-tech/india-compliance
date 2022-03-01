<template>
  <div class="india-compliance-account">
    <transition name="fade">
      <div class="loading-container" v-if="isLoading">
        <h1>India Compliance</h1>
        <h5>by Resilient Tech</h5>
        <Loading :radius="40" class="mt-3" />
      </div>
      <AccountPage v-else-if="isAuthenticated" />
      <AuthPage v-else />
    </transition>
  </div>
</template>

<script>
import AccountPage from "./account/AccountPage.vue";
import AuthPage from "./auth/AuthPage.vue";
import Loading from "./components/Loading.vue";
import authService from "./services/AuthService";

export default {
  components: {
    AuthPage,
    AccountPage,
    Loading,
  },

  data() {
    return {
      isAuthenticated: false,
      isLoading: true,
      account: {},
    };
  },

  async mounted() {
    this.isAuthenticated = await authService.isLoggedIn();
    this.isLoading = false;
  },
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

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.5s;
}
.fade-enter,
.fade-leave-to {
  opacity: 0;
}
</style>