<template>
  <div>
    <Form
      method="POST"
      formClass="contact-us"
      :formFields="formFields"
      :isLoading="isLoading"
      submitLabel="Send Message"
      @submit="onSubmit"
      ref="contactForm"
    />
  </div>
</template>

<script>
import Form from "../components/Form.vue";
export default {
  components: {
    Form,
  },

  data() {
    return {
      success: false,
      isLoading: false,
      error: null,
    };
  },

  props: { haveAccount: Boolean },
  computed: {
    formFields() {
      const fields = {
        email: {
          label: "Email",
          required: true,
          type: "email",
          validate(value) {
            if (value && !$nuxt.$validateEmail(value))
              return "Invalid Email Address!";
          },
        },
      };

      if (!this.haveAccount) {
        fields.gstin = {
          label: "GSTIN",
          required: true,
          type: "email",
          validate(value) {
            // TODO: validate GSTIN
          },
        };
      }
      return fields;
    },
  },
  // watch: {
  //   haveAccount(newVal, oldVal) {
  //     this.formFields = this.formFields;
  //   },

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