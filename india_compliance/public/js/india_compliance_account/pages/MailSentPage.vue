<template>
  <div class="mail-sent-page container text-center">
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
      <strong>{{ email }}</strong>.
      <br />
      Please click the button in that email to confirm your email address.
    </p>

    <div class="actions">
      <button @click.stop="changeEmail" class="btn btn-secondary btn-sm">
        <span v-html="change_icon"></span>
        Change Email
      </button>

      <button @click.stop="refresh" class="btn btn-primary btn-sm">
        <span v-html="refresh_icon"></span>
        Refresh
      </button>
    </div>
  </div>
</template>

<script>
export default {
  computed: {
    email() {
      const { session } = this.$store.state.auth;
      return session && session.email;
    },

    change_icon() {
      return frappe.utils.icon("change", "sm");
    },

    refresh_icon() {
      return frappe.utils.icon("refresh", "sm");
    },
  },
  methods: {
    async changeEmail() {
      await this.$store.dispatch("setSession", null);
      this.$router.replace({ name: "auth" });
    },

    async refresh() {
      await this.$store.dispatch("authenticate");
      this.$router.replace({ name: "auth" });
    }
  },
};
</script>

<style scoped>
.mail-sent-page {
  margin: 70px 0;
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

.actions button {
  margin-left: 5px;
}

.actions button:first-child {
  margin-left: 0;
}
</style>
