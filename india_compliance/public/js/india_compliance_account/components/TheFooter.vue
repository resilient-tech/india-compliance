<template>
  <footer class="container">
    <ul class="footer-menu">
      <!-- <li><a href="#">FAQs</a></li>
      <li><a href="#">Terms & Conditions</a></li>
      <li><a href="#">Privacy Policy</a></li> -->
    </ul>
    <div class="footer-logo">
      <p>ASP Services by</p>
      <a href="https://www.resilient.tech" target="_blank">
        <img src="" alt="footer-logo" />
      </a>
    </div>
  </footer>
</template>

<style scoped>
footer {
  margin-top: 5em;
  margin-bottom: 1em;
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

.footer-logo img {
  content: url("https://india-compliance.s3.ap-south-1.amazonaws.com/logo.png");
}

[data-theme="dark"] .footer-logo img {
  content: url("https://india-compliance.s3.ap-south-1.amazonaws.com/logo_dark.png");
}

@media screen and (max-width: 768px) {
  footer {
    flex-direction: column;
    align-items: center;
    padding: 2em 0;
  }
  .footer-menu {
    margin-top: 1em;
  }
  .footer-logo {
    margin-top: 1em;
  }
}
</style>
