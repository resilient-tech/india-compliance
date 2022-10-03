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
            <p class="label">Available Credits</p>
            <p class="value">{{ getReadableNumber(balance_credits, 0) }}</p>
          </div>
          <div class="subscription-details-item">
            <p class="label">Valid Upto</p>
            <p class="value">{{ valid_upto }}</p>
          </div>
          <router-link
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

export default {
  components: {
    PageTitle,
    Message,
    PreLoader,
  },

  data() {
    return {
      isLoading: true,
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

    balance_credits() {
      return this.subscriptionDetails.balance_credits;
    },

    valid_upto() {
      return frappe.datetime.str_to_user(this.subscriptionDetails.expiry_date);
    },

    message() {
      return this.$route.params.message;
    },
  },

  beforeRouteEnter(to, from, next) {
    next((vm) => {
      vm.$store.getters.isLoggedIn
        ? next()
        : next({ name: "auth", replace: true });
    });
  },

  async created() {
    if (!this.$store.getters.isLoggedIn) return;
    await this.$store.dispatch("fetchDetails", "subscription");
    this.isLoading = false;
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
