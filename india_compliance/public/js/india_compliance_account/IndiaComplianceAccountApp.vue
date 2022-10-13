<template>
  <div class="india-compliance-account">
    <div class="content">
          <transition name="fade" v-if="isLoading">
            <PreLoader />
          </transition>

          <router-view v-slot="{ Component }" v-else>
            <transition name="fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
      </div>
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
    this.isLoading = false;
  },
};
</script>

<style scoped>
.india-compliance-account {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

.india-compliance-account > .content {
  flex-grow: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
