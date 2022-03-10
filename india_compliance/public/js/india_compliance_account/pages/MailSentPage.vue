<template>
  <div class="contaier text-center mt-5">
    <img src="" alt="" />
    <h2>An email is on its way!</h2>
    <p>
      We sent an email to <b>{{ email }}</b
      >.
    </p>
    <p>
      If this email address has an account, you'll find a magic link that will
      sign you into the dashboard.
    </p>
    <p>This link expires in 24 hours, so be sure to use it soon.</p>
    <button @click.stop="changeEmail" class="btn btn-primary btn-sm">
      Change Email
    </button>
  </div>
</template>

<script>
export default {
  computed: {
    email() {
      return this.$route.query.email;
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
      if (!vm.$route.query.email || !vm.$store.getters.hasSession)
        return next({ name: "home", replace: true });
      return next();
    });
  },
};
</script>

<style scoped>
</style>