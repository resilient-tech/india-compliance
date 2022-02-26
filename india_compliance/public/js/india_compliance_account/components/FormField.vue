<template>
  <transition name="fade">
    <div class="form-group" :class="fieldClass">
      <input
        :type="inputType || 'text'"
        :name="name"
        :id="name"
        :class="getInputClass()"
        @input="updateInputValue"
        v-if="inputType === 'checkbox'"
        :checked="value"
      />
      <label
        :for="name"
        :class="'form-label' + required && 'reqd'"
        v-if="label"
      >
        {{ label }}
      </label>
      <input
        :type="inputType || 'text'"
        :name="name"
        :id="name"
        :class="getInputClass()"
        :value="value"
        @input="updateInputValue"
        :placeholder="placeholder"
        :required="required"
        v-if="['text', 'email'].includes(inputType)"
      />
      <span v-if="inputType === 'select'">
        <select
          :name="name"
          :id="name"
          :class="getInputClass()"
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
        :class="getInputClass()"
        :value="value"
        @input="updateInputValue"
        :placeholder="placeholder"
        :required="required"
        :rows="rows || 5"
        v-if="inputType === 'textarea'"
      >
      </textarea>
      <div class="input-error" v-if="error">
        <small>
          {{ error }}
        </small>
      </div>
    </div>
  </transition>
</template>

<style scoped>
label {
  font-size: 1rem;
}

.input-error {
  margin-top: 0.2rem;
  color: #ff3333;
}
</style>

<script>
export default {
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
      default: () => false,
    },
    label: String,
    placeholder: String,
    inputClass: String,
    fieldClass: String,
    error: String,
    rows: Number,
    accept: String,
    options: [Object, Array],
    validator: Function,
  },

  methods: {
    getInputClass() {
      return this.inputClass || "form-control";
    },
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
