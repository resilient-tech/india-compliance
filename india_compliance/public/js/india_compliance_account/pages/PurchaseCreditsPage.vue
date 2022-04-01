<template>
  <div class="container purchase-credits-page">
    <PreLoader v-if="isLoading" />
    <div v-else>
      <PageTitle title="Purchase API Credits" />
      <div class="main-content">
        <div class="card card-calculator">
          <div class="calculator">
            <p class="title">Calculator</p>
            <div class="form-group frappe-control">
              <div class="control-input">
                <input
                  type="number"
                  :step="creditsMultiplier"
                  :min="minOrderQty"
                  class="form-control"
                  v-model.number="creditsInputValue"
                />
              </div>
            </div>
            <p class="description">
              Credits to be purchased (to be entered in multiple of
              {{ creditsMultiplier }})
            </p>
            <button
              class="btn btn-primary btn-sm btn-block btn-tall mt-5"
              @click="handleButtonClick"
              :disabled="isRedirecting"
            >
              {{ buttonText }}
            </button>
          </div>
          <div class="calculator-result">
            <div class="row">
              <p class="col">Net Amount</p>
              <p class="col calculator-net-value">
                ₹ {{ netTotal.toFixed(2) }}
              </p>
            </div>
            <div class="row">
              <p class="col">GST @ {{ taxRate }}%</p>
              <p class="col calculator-net-value">₹ {{ tax.toFixed(2) }}</p>
            </div>
            <div class="calculator-total row">
              <p class="col">Amount Payable</p>
              <p class="col calculator-net-value">
                ₹ {{ grandTotal.toFixed(2) }}
              </p>
            </div>
          </div>
        </div>
        <div class="card card-pricing">
          <p class="title">Simple, Predictable Pricing</p>
          <table class="plan-detail">
            <tr>
              <td></td>
              <td class="plan-header">
                <p>Price per Credit</p>
                <p>(excl. GST)</p>
              </td>
            </tr>
            <tr v-for="(rate, credits, index) in rates" :key="index">
              <td class="plan-list">
                {{
                  index == 0
                    ? "First"
                    : credits == -1
                    ? "Any Additional"
                    : "Next"
                }}
                {{ credits != -1 ? credits : "" }} Credits
              </td>
              <td class="plan-list plan-price">
                ₹ {{ (rate / 100).toFixed(2) }}
              </td>
            </tr>
          </table>
          <div>
            <div>
              <p class="validity-header">Lifetime Validity<sup>*</sup></p>
              <p class="validity-footer">
                Initial validity of two years. Gets extended whenever you make
                the next purchase.
              </p>
            </div>
          </div>
          <a href="#" class="text-highlight text-right">learn more...</a>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import FormField from "../components/FormField.vue";
import PageTitle from "../components/PageTitle.vue";
import PreLoader from "../components/PreLoader.vue";

export default {
  components: {
    FormField,
    PageTitle,
    PreLoader,
  },

  data() {
    return {
      isLoading: true,
      credits: 0,
      creditsInputValue: 0,
      isRedirecting: false,
    };
  },

  computed: {
    calculatorDetails() {
      return this.$store.state.account.calculatorDetails || {};
    },

    creditsMultiplier() {
      return this.calculatorDetails.credits_multiplier;
    },

    minOrderQty() {
      return this.calculatorDetails.min_order_qty;
    },

    defaultCalculatorValue() {
      return this.calculatorDetails.default_calculator_value;
    },

    creditsValidity() {
      return this.calculatorDetails.credits_validity;
    },

    learnMoreUrl() {
      return this.calculatorDetails.learn_more_url;
    },

    rates() {
      return this.calculatorDetails.rates;
    },

    taxRate() {
      return this.calculatorDetails.tax_rate;
    },
    tax() {
      return (this.netTotal * this.taxRate) / 100;
    },

    netTotal() {
      return (this.credits * this.applicableRate) / 100;
    },

    applicableRate() {
      let slabs = Object.keys(this.rates).sort();
      const rates = Object.values(this.rates).sort().reverse();
      slabs.shift();
      slabs = slabs.map((slab) => parseInt(slab));
      return rates[bisect_left(slabs, this.credits)];
    },

    grandTotal() {
      return this.netTotal + this.tax;
    },

    buttonText() {
      if (this.isRedirecting) return "Redirecting...";
      if (this.isDirty) return "Calculate";
      return "Proceed to Payment";
    },

    isDirty() {
      return this.creditsInputValue != this.credits;
    },
  },

  methods: {
    handleButtonClick() {
      console.log(this.isDirty);
      if (this.isDirty) {
        this.updateCredits();
      } else {
        this.proceedToPayment();
      }
    },

    async proceedToPayment() {
      this.isRedirecting = true;
      await this.$store.dispatch("createOrder", {
        credits: this.credits,
        amount: this.grandTotal,
      });
      const { orderToken } = this.$store.state.account;
      if (!orderToken) return;

      this.isRedirecting = false;
      this.$router.push({
        name: "paymentPage",
        params: { orderToken },
      });
    },

    updateCredits() {
      this.credits = this.creditsInputValue;

      // credits only allowed to be in multiples of creditsMultiplier
      if (this.credits < this.minOrderQty) {
        this.credits = this.minOrderQty;
      } else if (this.credits % this.creditsMultiplier != 0) {
        this.credits =
          Math.ceil(this.credits / this.creditsMultiplier) *
          this.creditsMultiplier;
      }

      this.creditsInputValue = this.credits;
    },
  },

  async created() {
    await this.$store.dispatch("fetchCalculatorDetails");
    this.isLoading = false;
    this.credits = this.creditsInputValue = this.defaultCalculatorValue;
  },
};

// taken from: https://stackoverflow.com/a/58812425
function bisect_left(sortedList, value) {
  if (!sortedList.length) return 0;

  if (sortedList.length == 1) {
    return value > sortedList[0] ? 1 : 0;
  }

  let lbound = 0;
  let rbound = sortedList.length - 1;
  return bisect_left(lbound, rbound);

  // note that this function depends on closure over lbound and rbound
  // to work correctly
  function bisect_left(lb, rb) {
    if (rb - lb == 1) {
      if (sortedList[lb] < value && sortedList[rb] >= value) {
        return lb + 1;
      }

      if (sortedList[lb] == value) {
        return lb;
      }
    }

    if (sortedList[lb] > value) {
      return 0;
    }

    if (sortedList[rb] < value) {
      return sortedList.length;
    }

    let midPoint = lb + Math.floor((rb - lb) / 2);
    let midValue = sortedList[midPoint];

    if (value <= midValue) {
      rbound = midPoint;
    } else if (value > midValue) {
      lbound = midPoint;
    }

    return bisect_left(lbound, rbound);
  }
}
</script>

<style scoped>
.main-content {
  width: 100%;
  margin-top: 4em;
  display: flex;
  padding: 0 4em;
  column-gap: 6em;
  justify-content: stretch;
}

.btn-tall {
  font-size: 1.2em;
}
.card {
  min-height: 35em;
  justify-content: space-between;
  padding: 2em 3.5em;
  flex-grow: 1;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  background-color: var(--card-bg);
}
.card .title {
  font-size: 1.7em;
  font-weight: 600;
}
/* Card Calculator*/

.calculator .title {
  margin-bottom: 2em;
}
.calculator .description {
  margin-top: -0.5em;
}

.calculator .form-control {
  font-size: 1.4em;
  font-weight: 600;
  margin: 0;
}

.calculator .form-control::-webkit-inner-spin-button,
.calculator .form-control::-webkit-outer-spin-button {
  -webkit-appearance: none;
  -moz-appearance: none;
  appearance: none;
}

.calculator-net-value {
  font-weight: 600;
  text-align: end;
  font-size: 1.1em;
}
.calculator-total {
  font-size: 1.3em;
  font-weight: 600;
  margin-top: 0.9em;
}
.credits-input {
  padding: 22em;
}

/* Card Plan */

.card-pricing {
  max-width: 43%;
}

.plan-header {
  text-align: end;
  font-size: 0.75em;
  margin-bottom: 1.6em;
  font-weight: 400;
}
.plan-header p {
  margin-bottom: 0.4em;
}
.plan-detail {
  font-size: 1.2em;
  font-weight: 500;
  margin-top: 2em;
}
.plan-price {
  text-align: end;
  font-weight: 600;
}
.plan-list {
  padding-bottom: 0.9em;
}
.validity-header {
  font-size: 1.4em;
  font-weight: 500;
}
.validity-footer {
  font-size: 0.9em;
}
@media screen and (max-width: 1200px) {
  .main-content {
    column-gap: 4em;
    font-size: 0.9em;
  }
  .card {
    padding: 2em 2.5em;
  }
}
@media (max-width: 992px) {
  .purchase-credits-page {
    font-size: 0.8em;
  }
  .main-content {
    column-gap: 3em;
    padding: 2em 1.5em;
  }
}
@media (max-width: 768px) {
  .purchase-credits-page {
    font-size: 1em;
  }
  .main-content {
    flex-direction: column;
    row-gap: 3em;
  }
  .card {
    max-width: 100%;
  }
  .purchase-credits-page .title {
    text-align: center;
  }
}
@media (max-width: 576px) {
  .purchase-credits-page {
    font-size: 0.9em;
  }
}
@media (max-width: 400px) {
  .purchase-credits-page {
    font-size: 0.7em;
  }
}
</style>
