<template>
  <div class="container payment-page-page">
    <PageTitle title="Make Payment" class="title" />
    <div class="main-content">
      <div class="card card-payment-gateway" id="payment-gateway">
        <!-- Content -->
      </div>
      <div class="card card-billing">
        <PreLoader v-if="isLoading" />
        <div v-else>
          <div class="sub-heading">
            <p class="title">Billing Details</p>
            <a class="text-highlight text-right" @click.prevent="editAddress">
              Edit
            </a>
          </div>
          <div>
            <p class="company-title">{{ businessName }}</p>
            <div class="company-footer">
              <p>{{ addressLine1 }}</p>
              <p>{{ addressLine2 }}</p>
              <p>{{ city }}, {{ billingDetails.state }} - {{ pincode }}</p>
            </div>
            <p class="company-footer"><strong>GSTIN: </strong> {{ gstin }}</p>
          </div>
          <div class="sub-heading">
            <p class="title">Order Summary</p>
            <a class="text-highlight text-right">Edit</a>
          </div>
          <div class="order-summary">
            <div class="row">
              <p class="col">Credits Purchased</p>
              <p class="col order-summary-value">
                {{ getReadableNumber(orderDetails.credits, 0) }}
              </p>
            </div>
            <div class="row">
              <p class="col">Valid Upto</p>
              <p class="col order-summary-value">
                {{ creditsValidity }}
              </p>
            </div>
            <div class="row">
              <p class="col">Net Amount</p>
              <p class="col order-summary-value">
                ₹ {{ getReadableNumber(orderDetails.netTotal) }}
              </p>
            </div>
            <div class="row">
              <p class="col">GST @ {{ orderDetails.taxRate }}%</p>
              <p class="col order-summary-value">
                ₹ {{ getReadableNumber(orderDetails.tax) }}
              </p>
            </div>
            <div class="summary-footer row">
              <p class="col">Amount Payable</p>
              <p class="col order-summary-value">
                ₹ {{ getReadableNumber(orderDetails.grandTotal) }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import PageTitle from "../components/PageTitle.vue";
import PreLoader from "../components/PreLoader.vue";
import { verify_payment } from "../services/AccountService";
import { getReadableNumber } from "../utils";

export default {
  components: {
    PageTitle,
    PreLoader,
  },

  data() {
    return {
      isLoading: true,
    };
  },

  beforeRouteEnter(to, from, next) {
    if (to.params.order) return next();
    next({ name: "home", replace: true });
  },

  computed: {
    billingDetails() {
      return this.$store.state.account.billingDetails || {};
    },

    gstin() {
      return this.billingDetails.gstin;
    },

    businessName() {
      return this.billingDetails.business_name;
    },

    addressLine1() {
      return this.billingDetails.address_line1;
    },

    addressLine2() {
      return this.billingDetails.address_line2;
    },

    city() {
      return this.billingDetails.city;
    },

    state() {
      return this.billingDetails.state;
    },

    country() {
      return this.billingDetails.country;
    },

    pincode() {
      return this.billingDetails.pincode;
    },

    orderDetails() {
      return this.$route.params.order;
    },

    creditsValidity() {
      return frappe.datetime.str_to_user(this.orderDetails.validity);
    },
  },

  methods: {
    getReadableNumber,
    editAddress() {
      const dialog = new frappe.ui.Dialog({
        title: "Edit Billing Address",
        fields: [
          {
            label: "GSTIN",
            fieldname: "gstin",
            fieldtype: "Data",
            default: this.gstin,
          },
          {
            fieldtype: "Column Break",
          },
          {
            label: "Business Name",
            fieldname: "business_name",
            fieldtype: "Data",
            default: this.businessName,
          },
          {
            fieldtype: "Section Break",
          },
          {
            label: "Address 1",
            fieldname: "address_line1",
            fieldtype: "Data",
            default: this.addressLine1,
          },
          {
            label: "Address 2",
            fieldname: "address_line2",
            fieldtype: "Data",
            default: this.addressLine2,
          },
          {
            label: "City",
            fieldname: "city",
            fieldtype: "Data",
            default: this.city,
          },
          {
            fieldtype: "Column Break",
          },
          {
            label: "State",
            fieldname: "state",
            fieldtype: "Data",
            default: this.state,
          },
          {
            label: "Country",
            fieldname: "country",
            fieldtype: "Data",
            default: this.country,
          },
          {
            label: "Pincode",
            fieldname: "pincode",
            fieldtype: "Data",
            default: this.pincode,
          },
          {
            fieldtype: "Section Break",
          },
        ],
        primary_action_label: "Save",
        primary_action: async () => {
          await this.$store.dispatch(
            "updateBillingDetails",
            dialog.get_values()
          );
          console.log({ ...this.$store.state.account.billingDetails });
          dialog.hide();
        },
      }).show();
    },

    redirectToHome(message, color) {
      this.$router.push({
        name: "home",
        replace: true,
        params: { message: { message, color } },
      });
    },
    initCashFree(orderToken) {
      const style = getComputedStyle(document.body);
      const primaryColor = style.getPropertyValue("--primary");
      const cardBg = style.getPropertyValue("--card-bg");
      const fontFamily = style.getPropertyValue("--font-stack");
      const theme =
        document.documentElement.getAttribute("data-theme-mode") || "light";

      var dropConfig = {
        components: ["card", "netbanking", "app", "upi"],
        orderToken,
        onSuccess: async (data) => {
          if (data.order && data.order.status == "PAID") {
            const response = await verify_payment(data.order.orderId);
            if (!response.success || response.error) {
              this.redirectToHome(response.error, "red");
              return;
            }
            this.redirectToHome(
              `Thanks for purchasing API credits! We have successfully added <strong>${this.orderDetails.credits}</strong> credits to your account.`,
              "green"
            );
          }
        },
        onFailure: (data) => {
          // redirecting on order related errors
          if (data.order.errorText) {
            return this.redirectToHome(data.order.errorText, "red");
          }

          frappe.throw(
            data.transaction?.txMsg ||
              "Something went wrong, please try again later",
            "Payment Failed"
          );
        },
        style: {
          backgroundColor: cardBg.trim(),
          color: primaryColor.trim(),
          fontFamily: "Inter, sans-serif",
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
    },
  },

  created() {
    const script = document.createElement("script");
    script.setAttribute(
      "src",
      "https://sdk.cashfree.com/js/ui/1.0.26/dropinClient.sandbox.js"
    );
    document.head.appendChild(script);
    script.onload = async () => {
      await this.$store.dispatch("fetchDetails", "billing");
      this.isLoading = false;
      this.initCashFree(this.$route.params.order.token);
    };
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
  font-size: 1.3em;
  font-weight: bold;
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
