function update_erpnext_slides_settings() {
    const slide = erpnext.setup.slides_settings && erpnext.setup.slides_settings.slice(-1)[0];
    if (!slide) return;

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
    })
}

update_erpnext_slides_settings();
