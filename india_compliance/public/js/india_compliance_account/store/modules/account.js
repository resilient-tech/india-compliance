<<<<<<< HEAD
import {
    get_details,
    update_billing_details,
    create_order,
} from "../../services/AccountService";
=======
import { get_details, update_billing_details } from "../../services/AccountService";
import { create_order } from "../../services/AccountService";
>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)

export default {
    state: {
        subscriptionDetails: null,
        calculatorDetails: null,
        billingDetails: null,
<<<<<<< HEAD
        orderToken: null,
=======
        orderDetails: null,
        message: null,
>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)
    },

    mutations: {
        SET_SUBSCRIPTION_DETAILS(state, subscriptionDetails) {
            state.subscriptionDetails = subscriptionDetails;
        },

        SET_CALCULATOR_DETAILS(state, calculatorDetails) {
            state.calculatorDetails = calculatorDetails;
        },

        SET_BILLING_DETAILS(state, billingDetails) {
            state.billingDetails = billingDetails;
        },

<<<<<<< HEAD
        SET_ORDER_TOKEN(state, orderToken) {
            state.orderToken = orderToken;
=======
        SET_ORDER_DETAILS(state, orderDetails) {
            state.orderDetails = orderDetails;
        },

        SET_MESSAGE(state, message) {
            state.message = message;
>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)
        },
    },

    actions: {
        async fetchDetails({ commit }, type) {
            const response = await get_details(type);
<<<<<<< HEAD
            if (response.invalid_token)
                return this.dispatch("setApiSecret", null);

            if (!response.success || !response.message)
                frappe.throw();
=======
            if (response.invalid_token) return this.dispatch("setApiSecret", null);

            if (!response.success || !response.message) frappe.throw();
>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)
            commit(`SET_${type.toUpperCase()}_DETAILS`, response.message);
        },

        async updateBillingDetails({ commit }, billingDetails) {
            const response = await update_billing_details(billingDetails);
<<<<<<< HEAD
            if (response.invalid_token)
                return this.dispatch("setApiSecret", null);

            if (!response.success || !response.message)
                frappe.throw();
            commit("SET_BILLING_DETAILS", response.message);
            return response.message
        },

        async createOrder({ commit }, { credits, amount }) {
            const response = await create_order(credits, amount);
            if (response.invalid_token)
                return this.dispatch("setApiSecret", null);

            if (
                !response.success ||
                !response.message ||
                !response.message.order_token
            )
                frappe.throw();
            commit("SET_ORDER_TOKEN", response.message.order_token);
        },
=======
            if (response.invalid_token) return this.dispatch("setApiSecret", null);

            if (!response.success || !response.message) frappe.throw();
            commit("SET_BILLING_DETAILS", response.message);
            return response.message;
        },

        resetOrder({ commit }) {
            commit("SET_ORDER_DETAILS", null);
        },

        async createOrder({ commit }, orderDetails) {
            this.dispatch("resetOrder");

            const response = await create_order(
                orderDetails.credits,
                orderDetails.grandTotal
            );

            if (response.invalid_token) {
                this.dispatch("setApiSecret", null);
                return false;
            }

            if (!response.success || !response.message?.order_token) return false;

            orderDetails.token = response.message.order_token;
            commit("SET_ORDER_DETAILS", orderDetails);
            return true;
        },

        resetMessage({ commit }) {
            commit("SET_MESSAGE", null);
        },

        setMessage({ commit }, { message, color }) {
            commit("SET_MESSAGE",{ message, color});
        }

>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)
    },

    getters: {},
};
