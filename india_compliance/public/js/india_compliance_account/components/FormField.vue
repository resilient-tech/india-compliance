<template>
  <div class="form-group frappe-control" :class="formGroupClasses">
    <label
      :for="name"
      class="control-label"
      :class="required && 'reqd'"
      v-if="label"
    >
      {{ label }}
    </label>
    <div class="control-input">
      <input
        :type="inputType || 'text'"
        :name="name"
        :id="name"
        class="form-control"
        :class="inputClass"
        :value="value"
        :placeholder="placeholder"
        :required="required"
        v-if="['text', 'email'].includes(inputType)"
        @input="updateInputValue"
        @blur="validateField"
      />
      <span v-if="inputType === 'select'">
        <select
          :name="name"
          :id="name"
          class="form-control"
          :class="inputClass"
          :value="value"
          @input="updateInputValue"
          :required="required"
        >
          <option :value="option" v-for="option in options" :key="option">
            {{ option }}
          </option>
        </select>
      </span>
      <textarea
        :name="name"
        :id="name"
        class="form-control"
        :class="inputClass"
        :value="value"
        @input="updateInputValue"
        :placeholder="placeholder"
        :required="required"
        :rows="rows || 5"
        v-if="inputType === 'textarea'"
      >
      </textarea>

      <div class="sufix-icon">
        <Loading
          radius="15"
          color="var(--text-light)"
          stroke="1.8"
          v-if="isLoading"
        />
        <div v-else v-html="suffixIcon"></div>
      </div>
    </div>
    <div class="input-error" v-if="error">
      <small>
        {{ error }}
      </small>
    </div>
  </div>
</template>

<script>
import Loading from "./Loading.vue";
import { UiState } from "../constants";
export default {
  components: { Loading },
  props: {
    value: null,
    inputType: {
      type: String,
      validator(value) {
        return [
          "text",
          "email",
          "select",
          "textarea",
          "file",
          "checkbox",
        ].includes(value);
      },
      required: true,
    },
    name: {
      type: String,
      required: true,
    },
    required: {
      type: Boolean,
      default: false,
    },
    label: String,
    placeholder: String,
    inputClass: String,
    fieldClass: String,
    error: String,
    rows: Number,
    options: [Object, Array],
    validator: Function,
    state: {
      type: Number,
      default: UiState.initial,
    },
  },

  computed: {
    formGroupClasses() {
      if (!this.hasError) {
        return this.fieldClass;
      }
      return "has-error " + this.fieldClass;
    },

    isLoading() {
      return this.state === UiState.loading;
    },

    hasError() {
      return this.state === UiState.error || this.error;
    },

    suffixIcon() {
      if (this.state === UiState.success) {
        return '<i class="fa fa-check-circle" style="color: var(--green-500)"></i>';
      }
      if (this.state === UiState.error) {
        return '<i class="fa fa-times-circle" style="color: var(--red-500)"></i>';
      }
    },
  },

  methods: {
    updateInputValue(event) {
      this.$emit("input", event.target.value);
    },
    validateField() {
      if (this.validator) {
        this.validator(this.value);
      }
    },
  },

  updateInputValue(e, value) {
    this.$emit("input", value || e.target.value);
  },

  openFileSelector(name) {
    this.removeFile(name);
    this.$refs[name].click();
  },

  onFileChange(e) {
    const files = e.target.files || (e.dataTransfer && e.dataTransfer.files);
    this.$emit("validate", this.name, files[0]);
    this.updateInputValue(e, files[0]);
  },

  removeFile(name) {
    this.$refs[name].value = "";
    this.$emit("input", null);
  },
};
</script>

<style scoped>
.input-error {
  margin-top: 0.2rem;
  color: var(--red-500);
}

.control-input {
  position: relative;
  display: flex;
  align-items: center;
}

.sufix-icon {
  right: 0.5em;
  position: absolute;
  z-index: 10;
}
</style>