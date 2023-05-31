<template>
  <div class="form-group frappe-control" :class="this.hasError && 'has-error'">
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
        :value="modelValue"
        :placeholder="placeholder"
        :required="required"
        v-if="['text', 'email'].includes(inputType)"
        @input="$emit('update:modelValue', $event.target.value)"
        @blur="$emit('blur', $event.target.value.trim())"
      />
      <div class="suffix-icon">
        <Loading
          radius="15"
          color="var(--text-light)"
          stroke="1.8"
          v-if="isLoading"
        />
        <i
          class="fa fa-times-circle"
          style="color: var(--red-500)"
          v-else-if="hasError"
        ></i>
        <i
          class="fa fa-check-circle"
          style="color: var(--green-500)"
          v-else-if="isValid"
        ></i>
      </div>
    </div>
    <div class="input-error" v-if="error">
      {{ error }}
    </div>
  </div>
</template>

<script>
import Loading from "./Loading.vue";
import { UiState } from "../constants";
export default {
  components: { Loading },
  emits: ["update:modelValue", "blur"],
  props: {
    modelValue: String,
    inputType: {
      type: String,
      validator(value) {
        return ["text", "email"].includes(value);
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
    isLoading() {
      return this.state === UiState.loading;
    },
    hasError() {
      return this.state === UiState.error || this.error;
    },

    isValid() {
      return this.state === UiState.success;
    },
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

.suffix-icon {
  right: 0.5em;
  position: absolute;
  z-index: 10;
}
</style>
