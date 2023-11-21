$(document).on("app_ready", async function() {
    if (!frappe.boot.needs_audit_trail_notification) return;

    // let other processes finish
    await new Promise(resolve => setTimeout(resolve, 700));
    const d = frappe.msgprint({
        title: __("Configure Audit Trail"),
        indicator: "orange",
        message: __(
            `Dear India Compliance User,
            <br><br>

            In accordance with
            <a
              href='https://www.mca.gov.in/Ministry/pdf/AccountsAmendmentRules_24032021.pdf'
              target='_blank'
            >MCA Notification dated 24-03-2021</a>,
            all companies registered in India are required to maintain an Audit Trail
            of each and every transaction and creating an edit log of each change made
            in books of account w.e.f 1st April 2023.
            <br><br>
            To comply with this requirement, we have introduced a new setting called
            <strong>Enable Audit Trail</strong> in Accounts Settings.
            <br><br>
            <strong>Note:</strong>
            <ul>
                <li>Once this setting is enabled, it cannot be disabled.</li>
                <li>
                Enabling this setting will cause the following accounts setting
                to get disabled to ensure Audit Trail integrity:<br>
                <strong>
                Delete Accounting and Stock Ledger Entries on deletion of Transaction
                </strong>
                </li>
            </ul>


            Would you like to enable the same?`
        ),
    });

    d.set_primary_action(__("Enable Audit Trail"), () => {
        frappe.call({
            method: "india_compliance.audit_trail.utils.enable_audit_trail",
            callback(r) {
                if (r.exc) return;

                frappe.show_alert({
                    message: __("Audit Trail Enabled"),
                    indicator: "green",
                });
            },
        });

        d.hide();
    });

    d.set_secondary_action_label(__("Review Accounts Settings"));
    d.set_secondary_action(() => {
        frappe.set_route("Form", "Accounts Settings");
        d.hide();
    });

    d.onhide = () => {
        frappe.xcall("india_compliance.audit_trail.utils.disable_audit_trail_notification");
    };
});
