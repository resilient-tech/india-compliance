<template>
  <div class="container purchase-credits-page">
    <h2 class="page-heading">
      Purchase API Credits<span class="full-stop-highlight">.</span>
    </h2>
    <div class="main-content">
      <div class="row">
        <div class="col-md-7">
          
          <div class="card card-calculator">
            <p class="title">
              Calculator
            </p>
            <div class="calculator-input">
              <form>
                <FormField
                  input-type="email"
                  name="email"
                  placeholder="Email"
                />
                <p>
                  Credits to be purchased (to be entered in multiple of 2500)
                </p>
                <button class="btn btn-primary btn-sm btn-block">
                  Calculate
                </button>
              </form>
            </div>
            <div class="net-amount-small">
              <div class="row">
                <p class="col">Net Amount</p>
                <p class="col">₹ 1,000.00</p>
              </div>
              <div class="row">
                <p class="col">GST @ 18%</p>
                <p class="col">₹ 180.00</p>
              </div>
            </div>
            <div class="net-amount-large row">
                <p class="col">Amount Payable</p>
                <p class="col">₹ 1,180.00</p>
            </div>
          </div>
        </div>
        <div class="col-md-5">
          <div class="card card-pricing">
            <p class="title">
              Simple, Predictable Pricing
            </p>
            <div class="plan-header">
              <p>Price per Credit</p>
              <p>(excl. GST)</p>
            </div>
            <table class="plan-detail">
              <tr>
                <td>First 10,000 Credits</td>
                <td class="plan-price">₹ 0.50</td>
              </tr>
              <tr>
                <td>Next 40,000 Credits</td>
                <td class="plan-price">₹ 0.40</td>
              </tr>
              <tr>
                <td>Any Additional Credits</td>
                <td class="plan-price">₹ 0.30</td>
              </tr>
            </table>
            <div>
              <div class="col">
                <p class="row validity-head">Lifetime Validity *</p>
                <p class="row validity-footer">Initial validity of two years. Gets extended whenever you make the next purchase.</p>
              </div>
            </div>
            <div class="content-bottom">
                <a href="#">learn more...</a>
            </div>

         </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import FormField from "../components/FormField.vue";

export default {
  components: {
    FormField
  }
};
</script>

<style scoped>
.main-content {
  width: 100%;
  margin-top: 4em;
  display: flex;
  /* justify-content: center; */
  /* align-items: center; */
  padding: 0 4em;
  font-size: 1em;
}

.card {
  height: 30em;
  /* display: flex; */
  /* flex-direction: column; */
  justify-content: space-between;
  padding: 2em 3em;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  background-color: var(--card-bg);
}
.card .title {
  font-size: 1.7em;
  font-weight: 600;
}
.card-calculator{
  margin-right: 4em;
}

.page-heading {
  margin-top: 1.7em;
  font-size: 2em;
  text-align: left ;
}
.content-bottom{
  text-align: end;
}
.plan-header{
  text-align: end;
  font-size: 1em;
}
.plan-detail{
  font-size: 1.5em;
  font-weight: 500;
}
.plan-price{
  text-align: end;
  font-weight: 600;

}
</style>
