CUSTOM_FIELDS = {
    "Accounts Settings": [
        {
            "fieldname": "audit_trail_section",
            "fieldtype": "Section Break",
            "label": "Audit Trail",
            "insert_after": "invoice_and_billing_tab",
            "collapsible": 1,
            "collapsible_depends_on": "eval: !doc.enable_audit_trail",
        },
        {
            "fieldname": "enable_audit_trail",
            "fieldtype": "Check",
            "label": "Enable Audit Trail",
            "description": (
                "In accordance with <a"
                " href='https://egazette.gov.in/WriteReadData/2021/226081.pdf'"
                " target='_blank'> MCA Notification dated 24-03-2021</a>, enabling this"
                " feature will ensure that each change made to the books of account"
                " gets recorded. Once enabled, this feature cannot be disabled."
            ),
            "insert_after": "audit_trail_section",
        },
    ]
}
