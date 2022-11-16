<template>
  <div class="container ic-account-page purchase-credits-page">
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
                  :max="maxOrderQty"
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
          <div class="calculator-result mt-5">
            <div class="row">
              <p class="col">Net Amount</p>
              <p class="col calculator-net-value">
                ₹ {{ getReadableNumber(netTotal) }}
              </p>
            </div>
            <div class="row">
              <p class="col">GST @ {{ taxRate }}%</p>
              <p class="col calculator-net-value">₹ {{ getReadableNumber(tax) }}</p>
            </div>
            <div class="calculator-total row">
              <p class="col">Amount Payable</p>
              <p class="col calculator-net-value">
                ₹ {{ getReadableNumber(grandTotal) }}
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
                  index == 0 ? "First" : credits == Infinity ? "Any Additional" : "Next"
                }}
                {{ credits != Infinity ? credits : "" }} Credits
              </td>
              <td class="plan-list plan-price">
                ₹ {{ getReadableNumber(rate / 100) }}
              </td>
            </tr>
          </table>
          <div>
            <div>
              <p class="validity-header">Lifetime Validity<sup>*</sup></p>
              <p class="validity-footer">
                Initial validity is of {{ creditsValidity }} months. Gets extended
                whenever you make the next purchase.
              </p>
            </div>
          </div>
          <!-- <a :href="learnMoreUrl" target="_blank" class="text-highlight text-right">
            learn more...
          </a> -->
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import FormField from "../components/FormField.vue";
import PageTitle from "../components/PageTitle.vue";
import PreLoader from "../components/PreLoader.vue";
import { getReadableNumber } from "../utils";
import { create_order } from "../services/AccountService";

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

    maxOrderQty() {
      return this.calculatorDetails.max_order_qty;
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
      let net_total = 0;
      let total_credits = this.credits;

      for (let [credits, rate] of Object.entries(this.rates)) {
        credits = Math.min(total_credits, credits);
        net_total += (credits * rate) / 100;
        total_credits -= credits;
        if (!total_credits) break;
      }

      return net_total;
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
    getReadableNumber,
    handleButtonClick() {
      if (this.isDirty) {
        this.updateCredits();
      } else {
        this.proceedToPayment();
      }
    },

    async proceedToPayment() {
      this.isRedirecting = true;

      const orderDetails = {
        credits: this.credits,
        netTotal: this.netTotal,
        tax: this.tax,
        taxRate: this.taxRate,
        grandTotal: this.grandTotal,
        validity: frappe.datetime.add_months(
          frappe.datetime.now_date(),
          this.creditsValidity
        ),
      };

      const orderCreated = await this.$store.dispatch("createOrder", orderDetails);
      this.isRedirecting = false;

      if (!orderCreated) {
        frappe.throw(
          "Something went wrong while creating order, please contact support!"
        );
      }

      this.$router.push({ name: "paymentPage" });
    },

    updateCredits() {
      this.credits = this.creditsInputValue;

      // credits only allowed to be in multiples of creditsMultiplier
      if (this.credits > this.maxOrderQty) {
        this.credits = this.maxOrderQty;
      } else if (this.credits < this.minOrderQty) {
        this.credits = this.minOrderQty;
      } else if (this.credits % this.creditsMultiplier != 0) {
        this.credits =
          Math.ceil(this.credits / this.creditsMultiplier) * this.creditsMultiplier;
      }

      this.creditsInputValue = this.credits;
    },
  },

  async created() {
    await this.$store.dispatch("fetchDetails", "calculator");
    this.isLoading = false;
    this.credits = this.creditsInputValue = this.defaultCalculatorValue;
  },
};

</script>

<style scoped>
.btn-tall {
  font-size: 1.2em;
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

@media (max-width: 400px) {
  .card {
    min-height: 38em !important;
  }
}
</style>
