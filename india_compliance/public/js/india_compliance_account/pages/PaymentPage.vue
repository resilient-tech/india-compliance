<template>
  <div class="container payment-page-page">
    <PageTitle title="Make Payment" class="title" />
    <div class="main-content">
      <div class="card card-payment-gateway" id="payment-gateway">
        <!-- Content -->
      </div>
      <div class="card card-billing">
        <div class="sub-heading">
          <p class="title">Billing Details</p>
          <a class="text-highlight text-right" @click.prevent="editAddress"
            >Edit</a
          >
        </div>
        <div>
          <p class="company-title">Shalibhadra Metal Corporation</p>
          <p class="company-footer">
            8/A, Saimee Society No 2 Nr Pancharatna Apartment, Subhanpura
            Vadodara, Gujarat - 390023
          </p>
          <p class="company-footer"><strong>GSTIN: </strong>24AAUPV7468F1ZW</p>
        </div>
        <div class="sub-heading">
          <p class="title">Order Summary</p>
          <a class="text-highlight text-right">Edit</a>
        </div>
        <div class="order-summary">
          <div class="row">
            <p class="col">Credits Purchased</p>
            <p class="col order-summary-value">10,00,000</p>
          </div>
          <div class="row">
            <p class="col">Valid Upto</p>
            <p class="col order-summary-value">31.03.2023</p>
          </div>
          <div class="row">
            <p class="col">Net Amount</p>
            <p class="col order-summary-value">₹ 10,000.00</p>
          </div>
          <div class="row">
            <p class="col">GST @ 18%</p>
            <p class="col order-summary-value">₹ 1,800.00</p>
          </div>
          <div class="summary-footer row">
            <p class="col">Amount Payable</p>
            <p class="col order-summary-value">₹ 11,800.00</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import PageTitle from "../components/PageTitle.vue";
export default {
  components: {
    PageTitle,
  },

  //   beforeRouteEnter(to, from, next) {
  //     if (to.params.orderToken) return next();
  //     next({ name: "home", replace: true });
  //   },
  setup() {},
  methods: {
    editAddress() {
      let d = new frappe.ui.Dialog({
        title: "Edit Billing Address",
        fields: [
          {
            label: "GSTIN",
            fieldname: "gstin",
            fieldtype: "Data",
            default: "24AAUPV7468F1ZW",
          },
          {
            fieldtype: "Column Break",
          },
          {
            label: "Business Name",
            fieldname: "business_name",
            fieldtype: "Data",
            default: "Shalibhadra Metal Corporation",
          },
          {
            fieldtype: "Section Break",
          },
          {
            label: "Address 1",
            fieldname: "address_line1",
            fieldtype: "Data",
            default: "8/A, Saimee Society No 2",
          },
          {
            label: "Address 2",
            fieldname: "address_line2",
            fieldtype: "Data",
            default: "Nr Pancharatna Apartment, Subhanpura",
          },
          {
            label: "City",
            fieldname: "city",
            fieldtype: "Data",
            default: "Vadodara",
          },
          {
            fieldtype: "Column Break",
          },
          {
            label: "State",
            fieldname: "state",
            fieldtype: "Data",
            default: "Gujarat",
          },
          {
            label: "Country",
            fieldname: "country",
            fieldtype: "Data",
            default: "gst_return",
          },
          {
            label: "Pincode",
            fieldname: "pincode",
            fieldtype: "Data",
            default: "390023",
          },
          {
            fieldtype: "Section Break",
          },
        ],
        primary_action_label: "Save",
        primary_action() {
          d.hide();
        },
      });
      d.show();
    },
  },
  created() {
    const script = document.createElement("script");
    script.setAttribute(
      "src",
      "https://sdk.cashfree.com/js/ui/1.0.26/dropinClient.sandbox.js"
    );
    document.head.appendChild(script);
    script.onload = () => {
      initCashFree(this.$route.params.orderToken);
    };
  },
};

function initCashFree(orderToken) {
  const style = getComputedStyle(document.body);
  const primaryColor = style.getPropertyValue("--primary");
  const cardBg = style.getPropertyValue("--card-bg");
  const fontFamily = style.getPropertyValue("--font-stack");
  const theme =
    document.documentElement.getAttribute("data-theme-mode") || "light";

  var dropConfig = {
    components: ["order-details", "card", "netbanking", "app", "upi"],
    orderToken,
    onSuccess: function (data) {
      //on payment flow complete
    },
    onFailure: function (data) {
      //on failure during payment initiation
    },
    style: {
      backgroundColor: cardBg.trim(),
      color: primaryColor.trim(),
      fontFamily: fontFamily,
      fontSize: "14px",
      errorColor: "#ff0000",
      theme, //(or dark)
    },
  };

  const cashfree = new Cashfree();
  const paymentElement = document.getElementById("payment-gateway");
  cashfree.initialiseDropin(paymentElement, dropConfig);

  document
    .querySelector("#payment-gateway iframe")
    .setAttribute("scrolling", "no");
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

.card {
  max-height: 40em;
  justify-content: space-between;
  padding: 2em 3.5em;
  flex-grow: 1;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  background-color: var(--card-bg);
}
.card .title {
  font-size: 1.6em;
  font-weight: 600;
}
.card-payment-gateway {
  padding: 0;
  overflow-x: hidden;
  overflow-y: scroll;
}
.order-summary-value {
  font-weight: 600;
  text-align: end;
  font-size: 1.1em;
}

.card-billing {
  max-width: 43%;
}
.summary-footer {
  font-size: 1.3em;
  font-weight: 600;
  margin-top: 0.9em;
}

.plan-header {
  text-align: end;
  font-size: 0.75em;
  margin-bottom: 1.6em;
  font-weight: 400;
}
.company-title {
  font-size: 1.4em;
  font-weight: 500;
}
.company-footer {
  font-size: 1em;
  color: var(--text-light);
}
.sub-heading {
  display: flex;
  justify-content: space-between;
  flex-direction: row;
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
  .payment-page-page {
    font-size: 0.8em;
  }
  .main-content {
    column-gap: 3em;
    padding: 2em 1.5em;
  }
}
@media (max-width: 768px) {
  .payment-page-page {
    font-size: 1em;
  }
  .main-content {
    flex-direction: column;
    row-gap: 3em;
  }
  .card {
    max-width: 100%;
  }
  .payment-page-page .title {
    text-align: center;
  }
}
@media (max-width: 576px) {
  .payment-page-page {
    font-size: 0.9em;
  }
}
@media (max-width: 400px) {
  .payment-page-page {
    font-size: 0.7em;
  }
}
</style>
