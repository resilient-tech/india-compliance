<template>
  <form @submit.prevent="submitAuthForm">
    <FormField
      input-type="email"
      name="email"
      placeholder="Email"
      v-model.trim="email.value"
      :required="true"
      :error="email.error"
      :state="email.state"
      @blur="validateEmail"
    />
    <transition name="slide">
      <FormField
        v-if="!isAccountRegistered"
        input-type="text"
        name="gstin"
        placeholder="GSTIN"
        v-model.trim="gstin.value"
        :required="true"
        :error="gstin.error"
        :state="gstin.state"
      />
    </transition>
    <button
      class="btn btn-primary btn-sm btn-block"
      :disabled="actionDisabled"
      type="submit"
    >
      {{ computedSubmitLabel }}
    </button>
    <p class="server-error" v-if="error" v-html="error"></p>
  </form>
</template>

<script>
import FormField from "../FormField.vue";
import Loading from "../Loading.vue";
import { UiState } from "../../constants";
import {
  login,
  signup,
  check_free_trial_eligibility,
} from "../../services/AuthService";

export default {
  props: { isAccountRegistered: Boolean },

  components: { FormField, Loading },

  data() {
    return {
      email: {
        value: "",
        error: null,
        state: UiState.initial,
      },
      gstin: {
        value: "",
        error: null,
        state: UiState.initial,
      },

      isLoading: false,
      error: null,
      isRedirecting: false,
      submitLabel: "Continue",
    };
  },

  computed: {
    computedSubmitLabel() {
      if (this.isLoading) return "Loading...";
      if (this.isRedirecting) return "Redirecting...";

      if (this.isAccountRegistered) return "Login";
      return this.submitLabel;
    },

    actionDisabled() {
      if (
        this.isLoading ||
        this.isRedirecting ||
        this.hasInputError ||
        !this.isSucess
      )
        return true;
      if (this.isAccountRegistered) return !this.email.value;
      return !this.email.value || !this.gstin.value;
    },

    isSucess() {
      let _isSucess = this.email.state === UiState.success;
      if (!this.isAccountRegistered)
        _isSucess = _isSucess && this.gstin.state === UiState.success;
      return !!_isSucess;
    },

    hasInputError() {
      let _hasError = this.email.error;
      if (!this.isAccountRegistered) _hasError = _hasError || this.gstin.error;
      return !!_hasError;
    },
  },

  watch: {
    "gstin.value"(value) {
      this.error = null;
      this.validateGstin(value);
    },

    "email.value"(_) {
      this.error = null;
    },

    isAccountRegistered() {
      this.error = null;
    },
  },

  methods: {
    async submitAuthForm() {
      this.isLoading = true;
      this.error = null;
      if (this.hasInputError) return;

      const email = this.email.value;
      const gstin = this.gstin.value;

      let response;
      if (this.isAccountRegistered) response = await login(email);
      else response = await signup(email, gstin);

      this.isLoading = false;
      if (response.error) {
        this.error = response.error;
        return;
      }

      if (response.message && response.message.session) {
        await this.$store.dispatch("setSession", response.message.session);
      }

      this.isRedirecting = true;
      this.$router.push({
        name: "mailSent",
        query: { email },
      });
    },

    validateEmail(value) {
      const field = this.email;
      if (!value) value = field.value;
      field.state = UiState.loading;

      field.error = null;
      if (!value) field.error = "Email is required";
      else if (!validate_email(value)) field.error = "Invalid Email Address";

      field.state = field.error ? UiState.error : UiState.success;
    },

    async validateGstin(value) {
      const field = this.gstin;
      if (!value) value = field.value;

      field.error = null;
      field.state = UiState.loading;

      const set_error = (error_message) => {
        field.error = error_message;
        field.state = UiState.error;
      };

      if (!value) return set_error("GSTIN is required");

      value = india_compliance.validate_gstin(value);
      if (!value) return set_error("Invalid GSTIN detected");

      const { message, error } = await check_free_trial_eligibility(value);
      if (error) return set_error(error);

      this.submitLabel = message ? "Start Free Trial" : "Signup";
      field.state = UiState.success;
    },
  },
};
</script>

<style scoped>
.server-error {
  color: var(--red-500);
  font-size: var(--font-size-xs);
  text-align: center;
  margin: 0.5em 0 0 0;
}
</style>
