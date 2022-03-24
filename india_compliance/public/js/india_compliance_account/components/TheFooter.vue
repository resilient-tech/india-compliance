<template>
  <footer class="container">
    <ul class="footer-menu">
      <li><a href="">FAQs</a></li>
      <li><a href="">Terms & Conditions</a></li>
      <li><a href="">Pricvacy Policy</a></li>
    </ul>
    <div class="footer-logo">
      <p>ASP Services by</p>
      <img src="" alt="footer-logo" />
    </div>
  </footer>
</template>

<style scoped>
footer {
  margin-top: 5em;
  padding: 2em 3em 3em 3em;
  display: flex;
  width: 100%;
  justify-content: space-between;
}

.footer-menu {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  align-items: center;
}
.footer-logo p,
.footer-menu a {
  color: var(--text-light);
  opacity: 0.7;
}

.footer-menu li:not(:last-child)::after {
  content: "|";
  margin: 0 1em;
  color: var(--text-light);
  opacity: 0.7;
}

.footer-logo {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  max-width: 13em;
}

/* TODO: change the image url for light mode */
html[data-theme="light"] .footer-logo img {
  content: url("https://www.resilient.tech/_nuxt/img/logo_white.1d040bc.png");
}

html[data-theme="dark"] .footer-logo img {
  content: url("https://www.resilient.tech/_nuxt/img/logo_white.1d040bc.png");
}
</style>