frappe.provide("taxpayer_api");
frappe.provide("india_compliance");

taxpayer_api.call = async function (...args) {
    const response = await frappe.call(...args);
    const { message } = response;
    if (!["otp_requested", "invalid_otp"].includes(message?.error_type)) return response;

    await india_compliance.authenticate_otp(message.gstin, message.error_type);
    return taxpayer_api.call(...args);
}

Object.assign(india_compliance, {
    get_gstin_otp(company_gstin, error_type) {
        let description = `An OTP has been sent to the registered mobile/email for GSTIN ${company_gstin} for further authentication. Please provide OTP.`;
        if (error_type === "invalid_otp")
            description = `Invalid OTP was provided for GSTIN ${company_gstin}. Please try again.`;

        return new Promise(resolve => {
            const prompt = new frappe.ui.Dialog({
                title: __("Enter OTP"),
                fields: [
                    {
                        fieldtype: "Data",
                        label: __("One Time Password"),
                        fieldname: "otp",
                        reqd: 1,
                        description: description,
                    },
                ],
                primary_action_label: __("Submit"),
                primary_action(values) {
                    resolve(values.otp);
                    prompt.hide();
                },
                secondary_action_label: __("Resend OTP"),
                secondary_action() {
                    frappe.call({
                        method: "india_compliance.gst_india.utils.gstr_utils.request_otp",
                        args: { company_gstin },
                        callback: function () {
                            frappe.show_alert({
                                message: __("OTP has been resent."),
                                indicator: "green",
                            });
                            prompt.get_secondary_btn().addClass("disabled");
                        },
                    });
                },
            });
            prompt.show();
        });
    },

    async authenticate_otp(gstin, error_type = null) {
        if (!error_type) error_type = "otp_requested";

        let is_authenticated = false;

        while (!is_authenticated) {
            const otp = await this.get_gstin_otp(gstin, error_type);

            const { message } = await frappe.call({
                method: "india_compliance.gst_india.utils.gstr_utils.authenticate_otp",
                args: { company_gstin: gstin, otp: otp },
            });

            if (
                message &&
                ["otp_requested", "invalid_otp"].includes(message.error_type)
            ) {
                error_type = message.error_type;
                continue;
            }

            is_authenticated = true;
            return true;
        }
    },

    generate_evc_otp(company_gstin, pan, request_type) {
        return frappe.call({
            method: "india_compliance.gst_india.utils.gstr_utils.generate_evc_otp",
            args: {
                company_gstin: company_gstin,
                pan: pan,
                request_type: request_type,
            },
        });
    },
});

class IndiaComplianceForm extends frappe.ui.form.Form {
    taxpayer_api_call(method, args, callback) {
        // similar to frappe.ui.form.Form.prototype.call
        const opts = {
            method: method,
            doc: this.doc,
            args: args,
            callback: callback
        }

        opts.original_callback = opts.callback;
        opts.callback = (r) => {
            if (!r.exc) this.refresh_fields();
            opts.original_callback && opts.original_callback(r);
        }

        return taxpayer_api.call(opts);
    }
}

frappe.ui.form.Form = IndiaComplianceForm;