<template>
  <div class="container purchase-credits-page">
    <h2 class="page-heading">
      Purchase API Credits<span class="full-stop-highlight">.</span>
    </h2>
    <div class="main-content">
      <div class="content-wrapper-left">
        <div class="card card-calculator">
          <p class="title">
            Calculator
          </p>
          <div class="calculator-input">
            <form>
              <FormField
                input-type="text"
                inputClass="py-3"
                name="credits"
                placeholder="Credits"
              />
              <p class="caculator-input-footer">
                Credits to be purchased (to be entered in multiple of 2500)
              </p>
              <button class="btn btn-primary btn-sm btn-block btn-tall">
                Calculate
              </button>
            </form>
          </div>
          <div>
            <div class="row">
              <p class="col">Net Amount</p>
              <p class="col caculator-net-value">₹ 1,000.00</p>
            </div>
            <div class="row">
              <p class="col">GST @ 18%</p>
              <p class="col caculator-net-value">₹ 180.00</p>
            </div>
            <div class="calculator-total row">
              <p class="col">Amount Payable</p>
              <p class="col caculator-net-value">₹ 1,180.00</p>
            </div>
          </div>
        </div>
      </div>
      <div class="content-wrapper-right">
        <div class="card card-pricing">
          <p class="title">
            Simple, Predictable Pricing
          </p>
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
            <div >
              <p class="validity-header">Lifetime Validity*</p>
              <p class="validity-footer">Initial validity of two years. Gets extended whenever you make the next purchase.</p>
            </div>
          </div>
          <div class="content-bottom">
              <a href="#" class="text-highlight">learn more...</a>
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
  flex-direction: row;
  flex-wrap: wrap;
  padding: 0 4em;
  font-size: 1em;
}
.content-wrapper-right{
  flex-grow: 4;
  max-width: 45%;
}
.content-wrapper-left{
  flex-grow: 9;
}
.page-heading {
  margin-top: 1.7em;
  font-size: 2em;
  text-align: left ;
}
.content-bottom{
  text-align: end;
  color: blue;
}
.btn-tall{
  font-size: 1.2em;
}
.card {
  height: 35em;
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
/* Card Calculator*/

.card-calculator{
  margin-right: 2.5em;
}
.caculator-input-footer{
  margin-bottom: 2em;
}
.caculator-net-value{
  font-weight: 600;
  text-align: end;
  font-size: 1.1em;
}
.calculator-total{
  font-size: 1.3em;
  font-weight: 600;
  margin-top: 0.9em;
}
.credits-input{
  padding: 22em;
}

/* Card Plan*/

.plan-header{
  text-align: end;
  font-size: 0.6em;
  margin-bottom:1.6em ;
  font-weight: 400;
}
.plan-detail{
  font-size: 1.2em;
  font-weight: 500;
  margin-top: 2em;

}
.plan-price{
  text-align: end;
  font-weight: 600;
}
.plan-list{
  padding-bottom:0.9em ;
}
.validity-header{
  font-size: 1.4em;
  font-weight: 500;
}
.validity-footer{
  font-size: 1em;
}




/* .font-grey{
  color : #505050;
} */
</style>
