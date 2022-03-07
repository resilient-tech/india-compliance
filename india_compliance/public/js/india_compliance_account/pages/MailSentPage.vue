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
    <h4>Click Refresh after validating your account</h4>
    <button @click.stop="refresh" class="btn btn-primary btn-sm">
      Refresh
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
    async refresh() {
      location.reload();
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