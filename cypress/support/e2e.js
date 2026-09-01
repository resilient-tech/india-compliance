import "../../../frappe/cypress/support/e2e"; // eslint-disable-line

beforeEach(() => {
    cy.intercept("https://asp.resilient.tech/**", { forceNetworkError: true });
});
