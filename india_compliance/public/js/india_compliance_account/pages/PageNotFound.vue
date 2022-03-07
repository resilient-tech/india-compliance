<template>
  <div class="page-not-found">
    <h1 class="t-404">404</h1>
    <h1>Page Not Found</h1>
    <router-link to="/" class="btn btn-primary btn-sm m-2">
      Go to Home
    </router-link>
  </div>
</template>

<style scoped>
.page-not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: calc(80vh - 60px);
}

.t-404 {
  font-size: 11em;
}
</style>