export default {
    async get_api_secret() {
        return frappe
            .call("india_compliance.gst_india.get_gst_api_secret")
            .then(({ message }) => message)
            .catch(() => null);
    },

    login(email) {
        return india_compliance.gst_api.call("login", {
            body: { email },
        });
    },

    signup(email, gstin) {
        return india_compliance.gst_api.call("signup", {
            body: { email, gstin },
        });
    },

    async isEmailValidated(email) {
        const response = await india_compliance.gst_api.call(
            "is_email_validated",
            {
                body: { email },
            }
        );

        if (!response.success) return response;
    },

    validateGstin(value) {
        mockApiCall();
    },

    mockApiCall(response = {}, seconds = 1) {
        return new Promise((resolve) => {
            setTimeout(() => {
                resolve(response);
            }, 1000 * seconds);
        });
    },
};
