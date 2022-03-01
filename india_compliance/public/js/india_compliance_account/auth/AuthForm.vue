<template>
  <form action="POST" class="auth-form">
    <FormField
      inputType="email"
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
        inputType="text"
        name="gstin"
        label="GSTIN"
        v-model.trim="gstin.value"
        :required="true"
        :error="gstin.error"
        :state="gstin.state"
      />
    </transition>
    <a
      href
      class="btn btn-primary btn-sm btn-block"
      :class="actionDisabled && 'disabled'"
      type="submit"
      @click.stop.prevent="isAccountRegisted ? login : signup"
    >
      {{ submitLabel }}
    </a>
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
    };
  },

  computed: {
    submitLabel() {
      return this.isAccountRegisted ? "Login" : "Continue";
    },

    actionDisabled() {
      let _actionDisabled = !this.email.value;
      if (!this.isAccountRegisted)
        _actionDisabled = _actionDisabled || !this.gstin.value;
      return _actionDisabled || this.hasError;
    },

    hasError() {
      let _hasError = this.email.error;
      if (!this.isAccountRegisted) _hasError = _hasError || this.gstin.error;
      return !!_hasError;
    },
  },

  watch: {
    "gstin.value"(value) {
      this.validateGstin(value);
    },
  },

  methods: {
    async login() {
      this.validateEmail();

      if (this.hasError) return;
      const response = await authService.login(email);
    },

    async signup() {
      this.validateEmail();
      this.validateGstin();
      if (this.hasError) return;
      const response = await authService.signup(email, gstin);
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
</style>