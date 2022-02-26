<template>
  <div>
    <p class="title">Why you should opt in?</p>
    <ul class="features">
      <li :key="index" v-for="(feature, index) in features" class="feature">
        <CheckIcon class="feature-icon" />
        {{ feature }}
      </li>
    </ul>
  </div>
</template>
<script>
import CheckIcon from "../components/icons/CheckIcon.vue";
export default {
  components: { CheckIcon },
  created() {
    this.features = [
      "File GST from ERP",
      "Autofill amazing fields",
      "More features",
    ];
  },
};
</script>

<style scoped>
.marketing-info .title {
  font-size: 2.5em;
}
.features {
  list-style: none;
  padding-left: 1em;
}

.features .feature {
  font-size: 1.5em;
  margin: 0.7em 0;
  display: flex;
  align-items: center;
}

.features .feature-icon {
  fill: #5dbe46;
  width: 1em;
  height: 1em;
  margin-right: 0.4em;
}
</style>