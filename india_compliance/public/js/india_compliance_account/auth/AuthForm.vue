<template>
  <form class="auth-form" @submit.prevent="submitAuthForm">
    <FormField
      input-type="email"
      name="email"
      label="Email"
      placeholder="john@example.com"
      v-model.trim="email.value"
      :required="true"
      :error="email.error"
      :state="email.state"
      @blur="validateEmail"
    />
    <transition name="slide">
      <FormField
        v-if="!isAccountRegisted"
        input-type="text"
        name="gstin"
        label="GSTIN"
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
      {{ submitLabel }}
    </button>
    <p class="server-error" v-if="error" v-html="error"></p>
  </form>
</template>

<script>
import FormField from "../components/FormField.vue";
import Loading from "../components/Loading.vue";
import { UiState } from "../constants";
import authService from "../services/AuthService";

export default {
  props: { isAccountRegisted: Boolean },

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
    };
  },

  computed: {
    submitLabel() {
      if (this.isLoading) return "Loading...";
      return this.isAccountRegisted ? "Login" : "Continue";
    },

    actionDisabled() {
      if (this.isLoading || this.hasInputError || !this.isSucess) return true;
      if (this.isAccountRegisted) return !this.email.value;
      return !this.email.value || !this.gstin.value;
    },

    isSucess() {
      let _isSucess = this.email.state === UiState.success;
      if (!this.isAccountRegisted)
        _isSucess = _isSucess && this.gstin.state === UiState.success;
      return !!_isSucess;
    },

    hasInputError() {
      let _hasError = this.email.error;
      if (!this.isAccountRegisted) _hasError = _hasError || this.gstin.error;
      return !!_hasError;
    },
  },

  watch: {
    "gstin.value"(value) {
      this.validateGstin(value);
    },

    isAccountRegisted() {
      this.error = false;
    },
  },

  methods: {
    async submitAuthForm() {
      this.isLoading = true;
      this.error = false;
      try {
        if (this.isAccountRegisted) await this.login();
        else await this.signup();
      } catch (e) {
        this.error =
          e.message || "Something went wrong, Please try again later.";
      } finally {
        this.isLoading = false;
      }
    },

    async login() {
      if (this.hasInputError) return;
      const response = await authService.login(email);
      throw new Error("No Account found, please sign up instead.");
    },

    async signup() {
      if (this.hasInputError) return;
      const response = await authService.signup(email, gstin);
      throw new Error("Account is already exists, please login instead.");
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
      field.state = UiState.loading;

      field.error = null;
      if (!value) field.error = "GSTIN is required";
      else if (
        !validate_gst_number(value) ||
        !(await authService.validateGstin(value))
      )
        field.error = "Invalid GSTIN detected";
      field.state = field.error ? UiState.error : UiState.success;
    },
  },
};
</script>

<style scoped>
.slide-leave-active,
.slide-enter-active {
  overflow: hidden;
  transition: all 0.3s ease-in-out;
}

.slide-enter-to,
.slide-leave {
  max-height: 100px;
}

.slide-enter,
.slide-leave-to {
  max-height: 0;
  margin: 0;
}

.server-error {
  color: var(--red-500);
  font-size: var(--font-size-xs);
  text-align: center;
  margin: 0.5em 0 0 0;
}
</style>