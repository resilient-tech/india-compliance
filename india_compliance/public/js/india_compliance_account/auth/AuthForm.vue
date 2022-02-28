<template>
  <form action="POST" class="auth-form">
    <FormField
      inputType="email"
      name="email"
      label="Email"
      v-model="email"
      placeholder="john@example.com"
      :required="true"
      :error="emailError"
      :state="states.email"
      :validator="validateEmail"
    />
    <transition name="slide">
      <FormField
        v-if="!isAccountRegisted"
        inputType="text"
        name="gstin"
        label="GSTIN"
        v-model="gstin"
        :required="true"
        :error="gstinError"
        :state="states.gstin"
      />
    </transition>

    <a
      class="btn btn-primary btn-sm btn-block"
      :class="actionDisabled && 'disabled'"
      type="submit"
      href="#"
      @click.stop.prevent="onSubmit"
    >
      {{ submitLabel }}
    </a>
  </form>
</template>

<script>
import FormField from "../components/FormField.vue";
import Loading from "../components/Loading.vue";
import { UiState } from "../constants";
export default {
  props: { isAccountRegisted: Boolean },

  components: { FormField, Loading },

  data() {
    return {
      email: "",
      gstin: "",
      isLoading: false,
      emailError: "",
      gstinError: "",
      states: {
        email: UiState.initial,
        gstin: UiState.initial,
      },
    };
  },

  computed: {
    submitLabel() {
      return this.isAccountRegisted ? "Login" : "Continue";
    },

    actionDisabled() {
      let _actionDisabled = !this.email;
      if (!this.isAccountRegisted)
        _actionDisabled = _actionDisabled || !this.gstin;
      return _actionDisabled || this.hasError;
    },

    hasError() {
      let _hasError = this.emailError;
      if (this.isAccountRegisted) _hasError = _hasError || this.gstinError;
      return !!_hasError;
    },
  },

  methods: {
    async onSubmit() {
      this.validteForm();
      if (this.hasError) return;
    },

    validteForm() {
      this.validateEmail(this.email);
      if (!this.isAccountRegisted) this.validateGstin(this.gstin);
    },

    async validateEmail(value) {
      this.setFieldState("email", UiState.loading);

      if (!value) this.emailError = "Email is required!";
      else if (!window.validate_email(value))
        this.emailError = "Invalid Email Address!";
      else this.emailError = null;

      this.setFieldState(
        "email",
        this.emailError ? UiState.error : UiState.success
      );
    },

    async validateGstin(value) {
      this.setFieldState("gstin", UiState.loading);

      if (!value) this.gstinError = "GSTIN is required!";
      else this.gstinError = await this._validateGstin(value);

      this.setFieldState(
        "gstin",
        this.gstinError ? UiState.error : UiState.success
      );
    },

    _validateGstin(value) {
      return new Promise((resolve) => {
        setTimeout(() => {
          resolve(null);
        }, 1000);
      });
    },

    setFieldState(field, state) {
      if (this.states[field] !== state) this.$set(this.states, field, state);
    },
  },

  watch: {
    gstin(value) {
      if (!value) return;
      this.validateGstin(value);
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