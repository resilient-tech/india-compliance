<template>
  <div class="container auth-page">
    <h3 class="title text-center">{{ title }}</h3>
    <div class="main-content row">
      <MarketingInfo class="marketing-info" />
      <div class="v-divider d-none d-lg-block"></div>
      <div class="auth-form">
        <AuthForm :isAccountRegisted="isAccountRegisted" />
        <p class="change-view-btn">
          {{
            isAccountRegisted
              ? "Don't have an Account?"
              : "Already have an Account?"
          }}
          <a @click.prevent="toggleAuthView">
            {{ isAccountRegisted ? "Signup Now" : "Login Here" }}
          </a>
        </p>
      </div>
    </div>
  </div>
</template>

<script>
import AuthForm from "../components/auth/AuthForm.vue";
import MarketingInfo from "../components/auth/MarketingInfo.vue";

export default {
  components: {
    AuthForm,
    MarketingInfo,
  },

  data() {
    return {
      isAccountRegisted: false,
    };
  },

  computed: {
    title() {
      return this.isAccountRegisted
        ? "Namste!"
        : "Welcome, Let's get you started!";
    },
  },

  methods: {
    toggleAuthView() {
      this.isAccountRegisted = !this.isAccountRegisted;
    },

    async checkAccountRegisted(value) {
      this.isAccountRegisted = await _isEmailRegistered(value);
    },
  },

  beforeRouteEnter(to, from, next) {
    next((vm) => {
      if (vm.$store.getters.isLoggedIn) {
        return next({ name: "account", replace: true });
      }

      const { session } = vm.$store.state.auth;
      if (session) {
        return next({
          name: "mailSent",
          replace: true,
          query: { email: session.email },
        });
      }

      next();
    });
  },
};
</script>

<style scoped>
.auth-page .title {
  margin: 5em 0 3em;
}

.marketing-info,
.auth-form {
  margin: 3em 0;
}

.main-content {
  display: flex;
  justify-content: center;
}

@media (max-width: 991px) {
  .main-content {
    flex-direction: column;
    align-items: center;
  }

  .main-content * {
    margin: 1em 0;
  }
}

.auth-form {
  width: 400px;
}
.v-divider {
  background-color: var(--gray-200);
  width: 2px;
  margin: 0 5em;
}

.change-view-btn {
  text-align: center;
  margin-top: 20px;
}

.change-view-btn a {
  color: var(--primary-color);
}
</style>
