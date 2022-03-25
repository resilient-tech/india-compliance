<template>
  <div class="container auth-page">
    <div class="page-heading">
      <h1 class="base-font">India Compliance Account.</h1>
    </div>
    <div class="main-content">
       <div class="card">
        <h3 class="title text-center grey-text" >
          Last Updated On 25-05-2022 11:23 PM 
          <a href="#"> Refesh </a>
        </h3>
        <h4>Available Credits</h4>
        <h2>5000</h2>
        <h4>Valid Upto</h4>
        <h2>25-02-2023</h2>
        <button class="btn btn-primary btn-sm">Buy Credits</button>

      </div>
      <div class="card card-right">
        <h3 class="">
          Actions
        </h3>
        <ul style="list-style-type:none;">
          <li>
            <p class="">Show Usage</p>
          </li>
          <li>
            <p class="">Check API Status</p>
          </li>
          <li>
            <p class="">Community Forum</p>
          </li>
          <li>
            <p class="">Report a Bug</p>
          </li>
          <li>
            <p class="">Get API Support</p>
          </li>
        </ul>

      </div>
    </div>
  </div>
</template>

<script>
import Loading from '../components/Loading.vue';
export default {
  components: { Loading },
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
  width: 100%;
  margin-top: 1em;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 0 4em;
  font-size: 1em;
}

.card {
  min-width: 585px;
  height: 30em;
  margin: 2em;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 30px 0;
  border-radius: var(--border-radius-md);
  box-shadow: var(--card-shadow);
  background-color: var(--card-bg);
}
.card .card-right {
  align-items: left;
}
/* .card .card-left {
  
} */
.card .title {
  font-size: 1.7em;
}

.card .title .text-highlight {
  font-size: 1.2em;
}

.card form {
  width: 100%;
  max-width: 585px;
}

.grey-text {
  color: #A0A0A0;
  font-weight: 300;
  font-size: 20px;
  line-height: 60px;
  font-size: 20px;
  margin: 2em;
  margin-top: 1em;
}
.page-heading {
  margin-top: 3em;
}
.base-font {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 600;
  font-size: 36px;
  line-height: 56px;
  /* or 156% */

  display: flex;
  align-items: center;

  color: #000000;
}
.change-view-btn {
  text-align: center;
  margin-top: 20px;
}

.change-view-btn a {
  color: var(--primary-color);
}

@media (max-width: 991px) {
  .main-content {
    flex-direction: column;
    align-items: center;
    /* margin-top: 1 em; */
    font-size: 0.9em;
    padding: 0;
  }

  .main-content > * {
    margin: 1em 0;
  }

  .card {
    margin-left: 0;
  }
}

@media (max-width: 575px) {
  .container {
    padding-left: 0;
    padding-right: 0;
  }

  .card {
    height: 32em;
    border-radius: 0;
    width: 100%;
    padding-left: 15px;
    padding-right: 15px;
  }

  .main-content {
    font-size: 0.75em;
  }
}
</style>
