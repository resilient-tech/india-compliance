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

    validateGstin(value) {
        // either returns null or error message
        return new Promise((resolve) => {
            setTimeout(() => {
                resolve(true);
            }, 1000);
        });
    },
};
