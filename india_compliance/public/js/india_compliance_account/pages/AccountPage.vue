<template>
  <div class="container account-page">
    <h2 class="page-heading">
      India Compliance Account<span class="full-stop-highlight">.</span>
    </h2>
    <div class="main-content">
      <div class="card subscription-info">
        <p class="last-updated-text">
          Last Updated On 25-05-2022 11:23 PM
          <a href="#"> Refesh </a>
        </p>
        <div class="subscription-details-item">
          <p class="label">Available Credits</p>
          <p class="value">{{ balance_credits }}</p>
        </div>
        <div class="subscription-details-item">
          <p class="label">Valid Upto</p>
          <p class="value">{{ valid_upto }}</p>
        </div>
        <button class="btn btn-primary btn-sm btn-block">Buy Credits</button>
      </div>
      <div class="card">
        <h3 class="title">Actions</h3>
        <ul class="links">
          <a href="#"><li>Show Usage</li></a>
          <a href="#"><li>Check API Status</li></a>
          <a href="#"><li>Community Forum</li></a>
          <a href="#"><li>Report a Bug</li></a>
          <a href="#"><li>Get API Suppor</li></a>
        </ul>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  computed: {
    subscription_details() {
      return this.$store.state.account.subscription_details || {};
    },
    balance_credits() {
      return this.subscription_details.balance_credits;
    },
    valid_upto() {
      return frappe.datetime.str_to_user(this.subscription_details.expiry_date);
    },
  },

  beforeRouteEnter(to, from, next) {
    next((vm) => {
      vm.$store.getters.isLoggedIn
        ? next()
        : next({ name: "auth", replace: true });
    });
  },
};
</script>

<style scoped>
.main-content {
  margin-top: 1em;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0 4em;
  font-size: 1em;
}

.card {
  width: 30em;
  height: 26em;
  margin: 2em;
  display: flex;
  flex-direction: column;
  padding: 2em 3em;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  background-color: var(--card-bg);
}

.card .title {
  font-size: 1.7em;
  font-weight: 600;
}

.page-heading {
  margin-top: 3em;
  font-size: 2em;
  text-align: center;
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

@media (max-width: 992px) {
  .main-content {
    font-size: 0.9em;
    padding: 0;
  }
}
@media (max-width: 768px) {
  .main-content {
    flex-direction: column;
    align-items: center;
    margin-top: 1 em;
  }

  .main-content > * {
    margin: 1em 0;
  }

  .card {
    margin-left: 0;
  }
}

@media (max-width: 575px) {
  .main-content {
    font-size: 0.75em;
  }
}
</style>
