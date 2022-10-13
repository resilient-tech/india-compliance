<template>
  <div class="container auth-page">
    <div class="main-content">
      <MarketingInfo class="marketing-info" />
      <div class="auth-form">
        <h3 class="title text-center">
          {{ title }}<span class="full-stop-highlight">.</span>
        </h3>
        <AuthForm :isAccountRegistered="isAccountRegistered" />
        <p class="change-view-btn">
          {{
            isAccountRegistered
              ? "Don't have an account?"
              : "Already have an account?"
          }}
          <a @click.prevent="toggleAuthView">
            {{ isAccountRegistered ? "Sign Up" : "Login" }}
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
      isAccountRegistered: false,
    };
  },

  computed: {
    title() {
      return this.isAccountRegistered
        ? "Welcome back"
        : "Let's get you started";
    },
  },

  methods: {
    toggleAuthView() {
      this.isAccountRegistered = !this.isAccountRegistered;
    }
  },
};
</script>

<style scoped>
.container.auth-page {
  padding-top: 5em;
}
.main-content {
  width: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0 4em;
  font-size: 1em;
}

.marketing-info,
.auth-form {
  max-width: 50%;
}

.marketing-info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.auth-form {
  width: 400px;
  height: 28em;
  margin-left: 12em;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 45px 0;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  background-color: var(--card-bg);
}

.auth-form .title {
  font-size: 1.7em;
}

.auth-form form {
  width: 100%;
  max-width: 320px;
}

.change-view-btn {
  text-align: center;
  margin-top: 20px;
}

.change-view-btn a {
  color: var(--primary-color);
}

@media (max-width: 991px) {
  .main-content {
    flex-direction: column;
    align-items: center;
    margin-top: 5em;
    font-size: 0.9em;
    padding: 0;
  }

  .main-content > * {
    margin: 1em 0;
  }

  .marketing-info,
  .auth-form {
    max-width: 100%;
  }

  .marketing-info {
    text-align: center;
    align-items: center;
  }

  .auth-form {
    margin-left: 0;
  }
}

@media (max-width: 575px) {
  .container {
    padding-left: 0;
    padding-right: 0;
  }

  .auth-form {
    height: 32em;
    border-radius: 0;
    width: 100%;
    padding-left: 15px;
    padding-right: 15px;
  }

  .main-content {
    font-size: 0.75em;
  }
}
</style>
