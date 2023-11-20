<template>
  <div class="container ic-account-page account-page">
    <PreLoader v-if="isLoading" />
    <div v-else>
      <PageTitle title="India Compliance Account" />
      <Message
        v-if="message"
        :message="message.message"
        :color="message.color"
      />
      <div class="main-content">
        <div class="card subscription-info">
          <p class="last-updated-text">Last Updated On {{ last_synced_on }}</p>
          <div class="subscription-details-item">
            <p class="label">{{ is_unlimited_account ? 'Used Credits' : 'Available Credits' }}</p>
            <p class="value">{{ getReadableNumber(is_unlimited_account ? used_credits : balance_credits, 0)}}</p>
          </div>
          <div class="subscription-details-item">
            <p class="label">{{ is_unlimited_account ? 'Next Billing Date' : 'Valid Upto' }}</p>
            <p class="value" :class="{ 'mb-4': is_unlimited_account }">{{ valid_upto }}</p>
          </div>
          <router-link v-if="!is_unlimited_account"
            class="btn btn-primary btn-sm btn-block"
            to="/purchase-credits"
          >
            Purchase Credits
          </router-link>
        </div>
        <div class="card">
          <h3 class="title">Actions</h3>
          <ul class="links">
            <a @click.prevent="showUsage"><li>Review API Usage</li></a>
            <!-- <a href="#"><li>Check API Status</li></a> -->
            <a @click.prevent="openInvoiceDialog"><li>Invoice History</li></a>
            <a href="https://discuss.erpnext.com/c/erpnext/india-compliance/65"><li>Community Forum</li></a>
            <a href="https://github.com/resilient-tech/india-compliance/issues/new"><li>Report a Bug</li></a>
            <a href="mailto:api-support@indiacompliance.app"><li>Email Support</li></a>
            <a @click.prevent="logout"><li>Logout</li></a>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import PageTitle from "../components/PageTitle.vue";
import Message from "../components/Message.vue";
import PreLoader from "../components/PreLoader.vue";
import { getReadableNumber } from "../utils";
import { get_invoice_history, send_invoice_email } from '../services/AccountService';
import "../components/invoice_history_table.html";


export default {
  components: {
    PageTitle,
    Message,
    PreLoader,
  },

data() {
    return {
      isLoading: true,
      message: null,
    };
  },

  methods: {
    getReadableNumber,
    showUsage() {
      frappe.route_options = {
        integration_request_service: "India Compliance API",
      };
      frappe.set_route("List", "Integration Request");
    },
    logout() {
      frappe.confirm(
        "Are you sure you want to logout from your India Compliance Account?",
        async () => {
          await this.$store.dispatch("setApiSecret", null);
          this.$router.replace({ name: "auth" });
        }
      );
    },
    openInvoiceDialog() {
      const dialog = new frappe.ui.Dialog({
        title: __("Invoice History"),
        fields: [
          {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
          },
          {
            fieldname: "email",
            label: __("Email"),
            fieldtype: "Data",
            description: __("Invoice will be sent to this email address"),
            options: "Email",
            default: this.subscriptionDetails.email,
          },
          {
            fieldtype: "Column Break"
          },
          {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            reqd: 1,
            default: frappe.datetime.get_today(),
          },
          {
            label: __("Invoice History"),
            fieldtype: "Section Break",
          },
          {
            fieldname: "invoice_history",
            label: __("Invoice History"),
            fieldtype: "HTML",
            hidden: 1,
          }
        ],
        primary_action_label: __("Get Invoice History"),
        primary_action: async (values) => {
          const { from_date, to_date } = values;

          if (from_date > to_date)
            frappe.throw(__("From Date cannot be greater than To Date"));

          const response = await get_invoice_history(from_date, to_date);
          const data = response.message?.length > 0 ? response.message : null;
          const invoiceHistoryTable = frappe.render_template("invoice_history_table", {data_array: data});
          const invoice_history = dialog.fields_dict.invoice_history

          invoice_history.html(invoiceHistoryTable);
          invoice_history.df.hidden = 0;
          invoice_history.$wrapper.ready(function () {
            $('.get-invoice').click(async function () {
              const invoice_name = $(this).data('invoice-name');
              const email = dialog.get_value('email');

              const response = await send_invoice_email(invoice_name, email);
              if (response.success) {
                frappe.msgprint({
                  title: __("Success"),
                  message: __("Invoice {0} sent successfully.", [invoice_name]),
                  indicator: "green",
                });
              }
            });
          });
          dialog.refresh();
        },
      });
      dialog.show();
    }
  },
  computed: {
    last_synced_on() {
      // TODO: set based on user datetime format?
      let { last_usage_synced_on } = this.subscriptionDetails;
      last_usage_synced_on = last_usage_synced_on
        ? moment.unix(last_usage_synced_on)
        : moment();

      return last_usage_synced_on.format("DD-MM-YYYY HH:mm A");
    },

    subscriptionDetails() {
      return this.$store.state.account.subscriptionDetails || {};
    },

    is_unlimited_account() {
      return this.subscriptionDetails.total_credits === -1;
    },

    used_credits() {
      return this.subscriptionDetails.used_credits;
    },

    balance_credits() {
      return this.subscriptionDetails.balance_credits;
    },

    valid_upto() {
      return frappe.datetime.str_to_user(this.subscriptionDetails.expiry_date);
    },
  },

  async created() {
    await this.$store.dispatch("fetchDetails", "subscription");
    this.isLoading = false;

    this.message = this.$store.state.account.message;
    this.$store.dispatch("resetMessage");
  },
};
</script>

<style scoped>
.ic-account-page .main-content .card {
  min-height: 26em;
}

.subscription-info {
  align-items: center;
  text-align: center;
  justify-content: space-between;
}

.subscription-info .last-updated-text {
  color: var(--gray-500);
}
.subscription-info .last-updated-text a {
  color: var(--text-light);
}

.subscription-details-item {
  font-weight: 600;
  font-size: 1.2em;
}

.subscription-details-item .value {
  font-size: 1.6em;
  color: var(--text-color);
}

.links {
  list-style: none;
  padding: 0;
  margin: 0;
}

.links li {
  margin: 1.2em 0;
  transition-duration: 0.3s;
}

.links a {
  font-size: 1.3em;
  font-weight: 500;
  color: var(--text-light);
}
.links a:hover {
  color: var(--text-color);
  color: var(--primary);
  text-decoration: none;
}
.links a:hover li {
  margin-left: 0.3em;
}
</style>
