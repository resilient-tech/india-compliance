<template>
  <div class="container purchase-credits-page">
    <PageTitle title="Purchase API Credits" />
    <div class="main-content">
      <div class="card card-calculator">
        <div class="calculator">
          <p class="title">Calculator</p>
          <div class="form-group frappe-control">
            <div class="control-input">
              <input
                type="number"
                step="2500"
                min="2500"
                class="form-control"
              />
            </div>
          </div>
          <p class="description">
            Credits to be purchased (to be entered in multiple of 2500)
          </p>
          <button class="btn btn-primary btn-sm btn-block btn-tall mt-5">
            Calculate
          </button>
        </div>
        <div class="calculator-result">
          <div class="row">
            <p class="col">Net Amount</p>
            <p class="col calculator-net-value">₹ 1,000.00</p>
          </div>
          <div class="row">
            <p class="col">GST @ 18%</p>
            <p class="col calculator-net-value">₹ 180.00</p>
          </div>
          <div class="calculator-total row">
            <p class="col">Amount Payable</p>
            <p class="col calculator-net-value">₹ 1,180.00</p>
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
          <tr>
            <td class="plan-list">First 10,000 Credits</td>
            <td class="plan-list plan-price">₹ 0.50</td>
          </tr>
          <tr>
            <td class="plan-list">Next 40,000 Credits</td>
            <td class="plan-list plan-price">₹ 0.40</td>
          </tr>
          <tr>
            <td class="plan-list">Any Additional Credits</td>
            <td class="plan-list plan-price">₹ 0.30</td>
          </tr>
        </table>
        <div>
          <div>
            <p class="validity-header">Lifetime Validity<sup>*</sup></p>
            <p class="validity-footer">
              Initial validity of two years. Gets extended whenever you make the
              next purchase.
            </p>
          </div>
        </div>
        <a href="#" class="text-highlight text-right">learn more...</a>
      </div>
    </div>
  </div>
</template>

<script>
import FormField from "../components/FormField.vue";
import PageTitle from "../components/PageTitle.vue";

export default {
  components: {
    FormField,
    PageTitle,
  },
};
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
  height: 35em;
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
</style>
