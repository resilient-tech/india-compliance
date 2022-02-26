<template>
  <div class="signup-form">
    <Form
      method="POST"
      formClass="signup"
      v-bind:formFields="formFields"
      v-bind:isLoading="isLoading"
      @submit="onSubmit"
      submitLabel="Sign up"
      ref="signupForm"
    />
    <p class="login-btn">
      Already Have an Account? <a @click.prevent="changeAuthView">Login Here</a>
    </p>
  </div>
</template>

<script>
import Form from "../components/Form.vue";
export default {
  props: {
    changeAuthView: {
      type: Function,
    },
  },
  data() {
    return {
      success: false,
      isLoading: false,
      error: null,
    };
  },
  components: {
    Form,
  },

  computed: {
    formFields() {
      return {
        email: {
          label: "Email",
          required: true,
          type: "email",
          placeholder: "john@example.com",
          validate(value) {
            if (value && !frappe.utils.validate_type(value, "email"))
              return "Invalid Email Address!";
          },
        },
        gstin: {
          label: "GSTIN",
          required: true,
          type: "email",
          validate(value) {
            // TODO: validate GSTIN
          },
        },
      };
    },
  },
  methods: {
    async onSubmit({ email, gstin }) {
      this.success = false;
      this.error = null;
      const form = this.$refs.signupForm;
      if (!form.validate()) return;
      this.isLoading = true;
      try {
        // const response = await sendContactusInquiry(name, email, message);
        console.log(response);
        form.reset();
        this.success = true;
      } catch (e) {
        this.error =
          e.response?.data ?? "Something went wrong, Please try again later!";
      } finally {
        this.isLoading = false;
      }
    },
  },
};
</script>
<style scoped>
.login-btn {
  text-align: center;
  margin-top: 20px;
}

.login-btn a {
  color: var(--primary-color);
}
</style>