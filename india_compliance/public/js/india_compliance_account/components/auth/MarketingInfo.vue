<template>
  <div>
    <h1 class="title">
      Supercharge your
      <br />
      <span class="text-highlight">India Compliance</span>
    </h1>
    <ul class="features">
      <li :key="index" v-for="(feature, index) in features" class="feature">
        <MarketingInfoCheckIcon class="feature-icon" />
        {{ feature }}
      </li>
    </ul>
    <!-- <a
      class="learn-more-btn"
      href="https://indiacompliance.app"
      target="_blank"
    >
      Learn More...</a
    > -->
  </div>
</template>
<script>
import MarketingInfoCheckIcon from "./MarketingInfoCheckIcon.vue";

export default {
  components: { MarketingInfoCheckIcon },

  created() {
    this.features = [
      "Create e-Waybills from your ERP",
      "Automate e-Invoicing",
      "Autofill party information",
    ];
  },
};
</script>

<style scoped>
.marketing-info .title {
  font-size: 2.5em;
  font-weight: bold;
  line-height: 1.3;
}

.learn-more-btn {
  color: var(--primary-color);
  align-self: flex-end;
  font-size: 1.2em;
  margin-right: 1em;
}

.features {
  list-style: none;
  padding-left: 1em;
  text-align: start;
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

@media (max-width: 991px) {
  .learn-more-btn {
    align-self: center;
    margin-right: 0;
  }
}

@media (max-width: 575px) {
  .features .feature {
    font-size: 1.4em;
  }
}
</style>
