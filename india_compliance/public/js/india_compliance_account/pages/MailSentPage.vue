<template>
  <div class="mail-sent-page contaier text-center">
    <img
      class="mail-box-img"
      src="/assets/india_compliance/images/mail-box.png"
      alt=""
    />
    <h2 class="title">
      Verify your email<span class="text-highlight">.</span>
    </h2>
    <p class="message">
      Almost there! We've sent a verification email to
      <strong>{{ email }}</strong>
    </p>

    <button @click.stop="changeEmail" class="btn btn-primary btn-sm">
      Change Email
    </button>
  </div>
</template>

<script>
export default {
  computed: {
    email() {
      const { session } = this.$store.state.auth;
      return session && session.email;
    },
  },
  methods: {
    async changeEmail() {
      await this.$store.dispatch("setSession", null);
      this.$router.replace({ name: "auth" });
    },
  },

  beforeRouteEnter(to, from, next) {
    next((vm) => {
      if (!vm.$store.getters.hasSession)
        return next({ name: "home", replace: true });
      return next();
    });
  },
};
</script>

<style scoped>
.mail-sent-page {
  margin: 100px 0;
}

.mail-box-img {
  width: 15em;
  margin-bottom: 2em;
}

.title {
  font-weight: 600;
}

.message {
  font-weight: 300;
  font-size: 1.3em;
  margin-bottom: 2em;
}

@media screen and (max-width: 768px) {
  .message {
    font-size: 1.1em;
  }
}
</style>