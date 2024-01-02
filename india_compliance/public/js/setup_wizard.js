frappe.require("assets/india_compliance/js/quick_entry.js");
update_erpnext_slides_settings();

function update_erpnext_slides_settings() {
    const slide =
        erpnext.setup.slides_settings && erpnext.setup.slides_settings.slice(-1)[0];
    if (!slide) return;

    company_gstin_field = {
        fieldname: "company_gstin",
        fieldtype: "Data",
        label: __("Company GSTIN"),
    };

    const _index = can_fetch_gstin_info() ? 0 : 1;

    slide.fields.splice(_index, 0, company_gstin_field);

    slide.fields.splice(4, 0, {
        fieldname: "default_gst_rate",
        fieldtype: "Select",
        label: __("Default GST Rate"),
        options: [
            "0.0",
            "0.1",
            "0.25",
            "1.0",
            "1.5",
            "3.0",
            "5.0",
            "6.0",
            "7.5",
            "12.0",
            "18.0",
            "28.0",
        ],
        default: "18.0",
    });

    slide.fields.push({
        fieldname: "enable_audit_trail",
        fieldtype: "Check",
        label: __("Enable Audit Trail"),
        description: __(
            `In accordance with <a
              href='https://www.mca.gov.in/Ministry/pdf/AccountsAmendmentRules_24032021.pdf'
              target='_blank'
            > MCA Notification dated 24-03-2021</a>.<br>
            Once enabled, Audit Trail cannot be disabled.`
        ),
    });

    if (!can_fetch_gstin_info()) return;

    const _onload = slide.onload;
    slide.onload = function (slide) {
        _onload.call(this, slide);

        slide.get_input("company_gstin").on("change", async function () {
            autofill_company_info(slide);
        });
    };
}

async function autofill_company_info(slide) {
    const gstin = slide.get_input("company_gstin").val();
    const gstin_field = slide.get_field("company_gstin");
    const gstin_info = await get_gstin_info(gstin, false);

    if (gstin_info.business_name) {
        await slide.get_field("company_name").set_value(gstin_info.business_name);
        slide.get_input("company_name").trigger("input");
    }

    set_gstin_description(gstin_field, gstin_info.status);
}

function can_fetch_gstin_info() {
    return india_compliance.is_api_enabled() && !frappe.boot.gst_settings.sandbox_mode;
}
