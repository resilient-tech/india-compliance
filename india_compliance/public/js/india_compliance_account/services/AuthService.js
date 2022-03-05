export default {
    login(email) {
        return new Promise((resolve, reject) => {
            setTimeout(() => resolve(true), 1000);
        });
    },

    signup(email, gstin) {
        return new Promise((resolve, reject) => {
            setTimeout(() => resolve(true), 1000);
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
