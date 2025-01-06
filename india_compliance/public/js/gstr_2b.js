// const { resolve } = require("chart.js/helpers");

frappe.provide("gstr_2b");

RETRY_INTERVALS = [2000, 3000, 15000, 30000, 60000, 120000, 300000, 600000, 720000]; // 5 second, 15 second, 30 second, 1 min, 2 min, 5 min, 10 min, 12 min

Object.assign(gstr_2b, {
    regenerate: function (args) {
        taxpayer_api.call({
            method: "india_compliance.gst_india.utils.gstr_2.regenerate_gstr_2b",
            args: { gstin: args.gstin, return_period: args.return_period },
            callback: async function (r) {
                if (r.exc) return;

                let regeneration_status = null;
                if (r && r.message) {
                    const { reference_id } = r.message;
                    regeneration_status = await gstr_2b.check_regenerate_status(
                        args.gstin,
                        reference_id
                    );
                }

                args.callback && args.callback(regeneration_status, args);
            },
        });
    },

    check_regenerate_status: function (gstin, reference_id) {
        return new Promise(resolve => {
            gstr_2b._check_regenerate_status(gstin, reference_id, resolve);
        });
    },

    _check_regenerate_status: function (gstin, reference_id, retries = 0) {
        if (retries >= RETRY_INTERVALS.length) {
            return { status: "ER", error: "Failed to regenerate GSTR-2B" };
        }

        setTimeout(() => {
            frappe.call({
                method: "india_compliance.gst_india.utils.gstr_2.check_regenerate_status",
                args: { gstin, reference_id },
                callback: function (r) {
                    if (r.exc) return;
                    const { status_cd: status, err_msg: error } = r.message;
                    if (status === "IP")
                        return gstr_2b._check_regenerate_status(
                            gstin,
                            reference_id,
                            callback,
                            retries + 1
                        );

                    return { status, error };
                },
            });
        }, RETRY_INTERVALS[retries]);
    },
});
