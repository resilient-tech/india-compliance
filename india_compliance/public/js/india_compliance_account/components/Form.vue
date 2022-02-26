<template>
  <form :method="method || 'POST'" :class="formClass">
    <div class="fields">
      <FormField
        v-for="(options, name) in formFields"
        :key="name"
        :inputType="options.type || 'text'"
        :name="name"
        :label="options.label"
        :value="values[name]"
        @input="updateInputValue(name, $event)"
        :placeholder="options.placeholder"
        :required="options.required"
        :inputClass="options.class"
        :options="options.options"
        :rows="options.rows"
        :accept="options.accept"
        :error="errors[name]"
        @validate="validateField"
      />
    </div>
    <a
      class="btn btn-primary btn-sm btn-block"
      type="submit"
      v-if="!isLoading"
      @click.stop.prevent="submit()"
    >
      {{ submitLabel || "SUBMIT" }}
    </a>
    <Loading v-else />
  </form>
</template>

<script>
import FormField from "./FormField.vue";
export default {
  props: {
    method: {
      type: String,
      validator(value) {
        return ["GET", "POST", "get", "post"].includes(value);
      },
    },
    formFields: {
      type: Object,
      required: true,
      validator(value) {
        // TODO: validate formFields
        return true;
      },
    },
    submitLabel: {
      type: String,
      required: true,
    },
    formClass: String,
    isLoading: Boolean,
  },

  components: {
    FormField,
  },

  data() {
    return {
      submitted: false,
      errors: {},
      values: {},
    };
  },

  created() {
    this.reset();
  },

  hasErrors() {
    return this.errors.length;
  },

  methods: {
    updateInputValue(key, value) {
      this.$set(this.values, key, value);
    },

    submit() {
      this.$emit("submit", { ...this.values });
    },

    reset() {
      for (const [name, { value }] of Object.entries(this.formFields)) {
        this.updateInputValue(name, value);
      }
      this.errors = {};
    },

    validate() {
      this.errors = {};
      let hasErrors = false;
      for (const fieldname in this.formFields) {
        if (!this.validateField(fieldname) && !hasErrors) {
          hasErrors = true;
        }
      }
      return !hasErrors;
    },

    validateField(fieldname, value) {
      const field = this.formFields[fieldname];
      if (!value) value = this.values[fieldname];

      let error;
      if (field.required && !value) error = `${field.label} is required!`;
      if (field.validate && !error) error = field.validate(value);
      if (!error) return true;

      this.$set(this.errors, fieldname, error);
    },
  },
};
</script>