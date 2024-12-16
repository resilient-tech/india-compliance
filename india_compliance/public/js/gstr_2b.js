const { resolve } = require("chart.js/helpers");

frappe.provide("gstr_2b");

RETRY_INTERVALS = [2000, 3000, 15000, 30000, 60000, 120000, 300000, 600000, 720000]; // 5 second, 15 second, 30 second, 1 min, 2 min, 5 min, 10 min, 12 min

Object.assign(gstr_2b, {
	regenerate: function (gstin, return_period, callback) {
		let message = __("Regenerating GSTR-2B");
		if (return_period) message += __(" for period {0}", [return_period]);

		frappe.show_alert({ message: message, indicator: "blue" })

		frappe.call({
			method: "india_compliance.gst_india.utils.gstr_2.regenerate_gstr_2b",
			args: { gstin, return_period },
			callback: async function (r) {
				if (r.exc) return;

				const { reference_id } = r.message;
				await gstr_2b.check_regenerate_status(gstin, reference_id);

				callback && callback(gstin, return_period);
			},
		});
	},

	check_regenerate_status: function (gstin, reference_id) {
		return new Promise(resolve => {
			gstr_2b._check_regenerate_status(gstin, reference_id, resolve);
		});
	},

	_check_regenerate_status: function (gstin, reference_id, callback, retries = 0) {
		if (retries >= RETRY_INTERVALS.length) {
			frappe.show_alert({ message: __("Failed to regenerate GSTR-2B"), indicator: "red" });
			callback && callback();
			return;
		}

		setTimeout(() => {
			frappe.call({
				method: "india_compliance.gst_india.utils.gstr_2.check_regenerate_status",
				args: { gstin, reference_id },
				callback: function (r) {
					if (r.exc) return;
					const { status_cd: status, err_msg: error } = r.message;
					if (status === "IP") gstr_2b._check_regenerate_status(gstin, reference_id, callback, retries + 1);
					if (status === "ER") frappe.throw(error);

					frappe.show_alert({ message: __("GSTR-2B Regenerated"), indicator: "green" });
					callback && callback();
				}
			});
		}, RETRY_INTERVALS[retries]);
	},
});
