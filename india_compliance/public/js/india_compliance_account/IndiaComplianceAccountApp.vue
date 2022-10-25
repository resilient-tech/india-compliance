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
import { AUTH_ROUTES } from "./router";

export default {
  components: { PreLoader, TheFooter },

  data() {
    return {
      isLoading: true,
    };
  },

  watch: {
    async $route() {
      frappe.router.current_route = await frappe.router.parse();
      frappe.breadcrumbs.update();
    },
  },

  async created() {
    const guessRoute = to => {
      const routeToCompare = in_list(AUTH_ROUTES, to.name) ? to.name : "home";
      const guessedRoute = this.$store.getters.guessRouteName;

      if (routeToCompare !== guessedRoute) {
        return {
          name: guessedRoute,
          replace: true,
        }
      }
    };

    // check if user is logged in
    await this.$store.dispatch("authenticate");

    // redirect to appropriate page if current route is incorrect
    const newGuess = guessRoute(this.$route);
    if (newGuess) await this.$router.push(newGuess);

    // add beforeEach hook to router
    this.$router.beforeEach(guessRoute);

    // finish loading
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
