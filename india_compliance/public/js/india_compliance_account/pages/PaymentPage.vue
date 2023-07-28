<template>
  <div class="container ic-account-page payment-page">
    <PageTitle title="Make Payment" class="title" />
    <div class="main-content">
      <div class="card card-payment-gateway" id="payment-gateway">
        <!-- Content -->
      </div>
      <div class="card">
        <PreLoader v-if="isLoading" />
        <template v-else>
          <div class="billing-details">
            <div class="sub-heading">
              <p class="title">Billing Details</p>
              <a class="text-highlight text-right" @click.prevent="editAddress">
                Edit
              </a>
            </div>
            <div class="billing-details-body">
              <p class="company-title">{{ businessName }}</p>
              <div class="company-footer">
                <p>{{ addressLine1 }}</p>
                <p>{{ addressLine2 }}</p>
                <p>{{ city }}, {{ billingDetails.state }} - {{ pincode }}</p>
              </div>
              <p class="company-footer"><strong>GSTIN: </strong> {{ billingGstin }}</p>
            </div>
          </div>
          <div class="order-summary">
            <div class="sub-heading">
              <p class="title">Order Summary</p>
              <a @click="$router.back()" class="text-highlight text-right"> Edit </a>
            </div>
            <div class="order-summary-body">
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
        </template>
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
      orderDetails: null,
      isLoading: true,
      // TODO: fix reactivity of vuex store's state `billingDetails` and use computed property instead
      billingDetails: {},
    };
  },

  computed: {
    billingGstin() {
      return this.billingDetails.billing_gstin;
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

    creditsValidity() {
      return frappe.datetime.str_to_user(this.orderDetails.validity);
    },
  },


  methods: {
    getReadableNumber,
    editAddress() {
      const states = frappe.boot.india_state_options || [];
      const dialog = new frappe.ui.Dialog({
        title: "Edit Billing Address",
        fields: [
          {
            label: "GSTIN",
            fieldname: "billing_gstin",
            fieldtype: "Data",
            default: this.billingGstin,
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
            fieldtype: "Autocomplete",
            default: this.state,
            options: this.country.toLowerCase() === "india" ? states : [],
          },
          {
            label: "Country",
            fieldname: "country",
            fieldtype: "Data",
            default: this.country,
            onchange() {
              // TODO: fix in frappe needed to update dialog options
              dialog.set_df_property(
                "state",
                "options",
                this.value.toLowerCase() === "india" ? states : [],
              );
            },
          },
          {
            label: "Postal Code",
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
          const values = dialog.get_values();

          // hack: comparing two objects
          if (JSON.stringify(this.billingDetails) === JSON.stringify(values)) {
            dialog.hide();
            return;
          }

          this.billingDetails = values;
          await this.$store.dispatch("updateBillingDetails", values);

          dialog.hide();
          frappe.show_alert({
            message: "Billing Details updated successfully",
            indicator: "green",
          });
        },
      }).show();
    },

    redirectToHome(message, color) {
      this.$store.dispatch("setMessage", { message, color });
      this.$router.replace({ name: "home" });
    },

    initCashFree(orderToken) {
      const style = getComputedStyle(document.body);
      const primaryColor = style.getPropertyValue("--primary");
      const cardBg = style.getPropertyValue("--card-bg");
      const theme = document.documentElement.getAttribute("data-theme-mode") || "light";

      const dropConfig = {
        components: ["card", "netbanking", "app", "upi"],
        orderToken,
        onSuccess: async data => {
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
        onFailure: data => {
          // redirecting on order related errors
          if (data.order.errorText) {
            return this.redirectToHome(data.order.errorText, "red");
          }

          frappe.throw(
            data.transaction?.txMsg || "Something went wrong, please try again later",
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

      document.querySelector("#payment-gateway iframe").setAttribute("scrolling", "no");
    },
  },

  created() {
    this.orderDetails = this.$store.state.account.orderDetails;
    this.$store.dispatch("resetOrder");

    if (!this.orderDetails || !this.orderDetails.token) {
      return this.redirectToHome("Invalid order details", "red");
    }

    const script = document.createElement("script");
    script.setAttribute(
      "src",
      "https://sdk.cashfree.com/js/ui/1.0.26/dropinClient.prod.js"
    );
    document.head.appendChild(script);
    script.onload = async () => {
      this.initCashFree(this.orderDetails.token);
      await this.$store.dispatch("fetchDetails", "billing");
      this.isLoading = false;
      this.billingDetails = this.$store.state.account.billingDetails;
    };
  },
};
</script>

<style scoped>
.card {
  max-height: 40em;
}

.card-payment-gateway {
  padding: 0 !important;
  overflow-x: hidden;
  overflow-y: scroll;
}

.order-summary-value {
  font-weight: 600;
  text-align: end;
  font-size: 1.1em;
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
</style>
