<template>
  <div class="container auth-page">
    <h3 class="title text-center">{{ title }}</h3>
    <div class="main-content">
      <MarketingInfo class="marketing-info" />
      <div class="v-divider"></div>
      <div class="auth-form">
        <AuthForm :haveAccount="haveAccount" />
        <p class="change-view-btn">
          {{
            haveAccount ? "Don't Have an Account?" : "Already Have an Account?"
          }}
          <a @click.prevent="changeAuthView">
            {{ haveAccount ? "Signup Now" : "Login Here" }}
          </a>
        </p>
      </div>
    </div>
  </div>
</template>

<script>
import AuthForm from "./AuthForm.vue";
import MarketingInfo from "./MarketingInfo.vue";
import Signup from "./Signup.vue";
export default {
  data() {
    return {
      haveAccount: false,
    };
  },
  computed: {
    title() {
      return this.haveAccount ? "Namste!" : "Welcome, Let's get you started!";
    },
  },
  methods: {
    changeAuthView() {
      this.haveAccount = !this.haveAccount;
    },
  },
  components: {
    AuthForm,
    Signup,
    MarketingInfo,
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

.auth-form {
  min-width: 400px;
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
