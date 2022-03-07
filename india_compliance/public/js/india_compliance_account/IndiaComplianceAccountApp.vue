<template>
  <div class="india-compliance-account">
    <transition name="fade">
      <Startup v-if="isLoading" />
      <transition name="fade" mode="out-in" v-else>
        <keep-alive>
          <router-view />
        </keep-alive>
      </transition>
    </transition>
  </div>
</template>

<script>
import Startup from "./pages/Startup.vue";

export default {
  components: { Startup },

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

  async mounted() {
    await this.$store.dispatch("initAuth");
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