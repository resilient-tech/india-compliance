<template>
  <div class="india-compliance-account">
    <transition name="fade">
      <PreLoader v-if="isLoading" />
      <transition name="fade" mode="out-in" v-else>
        <router-view />
      </transition>
    </transition>
    <TheFooter />
  </div>
</template>

<script>
import PreLoader from "./components/PreLoader.vue";
import TheFooter from "./components/TheFooter.vue";

export default {
  components: { PreLoader, TheFooter },

  data() {
    return {
      isLoading: true,
    };
  },

  watch: {
    $route() {
      frappe.router.current_route = frappe.router.parse();
      frappe.breadcrumbs.update();
    },
  },

  async created() {
    await this.$store.dispatch("initAuth");
    if (this.$store.getters.isLoggedIn) {
      await this.$store.dispatch("initAccount");
    }
    this.isLoading = false;
  },
};
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter,
.fade-leave-to {
  opacity: 0;
}
</style>