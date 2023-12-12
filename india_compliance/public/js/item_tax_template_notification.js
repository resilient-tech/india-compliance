// TODO: Update documentation links
$(document).on("app_ready", async function () {
    if (!frappe.boot.needs_item_tax_template_notification) return;

    // let other processes finish
    await new Promise(resolve => setTimeout(resolve, 700));
    const d = frappe.msgprint({
        title: __("🚨 Important: Changes to Item Tax Template"),
        indicator: "orange",
        message: __(
            `Dear India Compliance User,
            <br><br>

			We are pleased to inform you about a recent update on how Item Tax Templates are
			maintained in India Compliance App.
			<br><br>

			Documentation Link:
            <a
              href='https://www.mca.gov.in/Ministry/pdf/AccountsAmendmentRules_24032021.pdf'
              target='_blank'
            >MCA Notification dated 24-03-2021</a>,
			<br>

			Migration Guide:
			<a
				href='https://github.com/frappe/erpnext/wiki/Migrating-from-version-13-to-version-14#item-tax-template-changes'
				target='_blank'
			>Migrating from version 13 to version 14</a>
			<br><br>

			<strong>Breaking Change:</strong>
			<ul>
				<li>GST Category for Nil-Rated, Exempted and Non-GST is introduced in Item Tax Template</li>
				<li>Nil-Rated items are differentiated from Exempted for GST (configrable from Item Tax Template)</li>
				<li><strong>Assumption Made:</strong> All transactions that were marked as Nil or Exempt,
				are now marked as Nil-Rated.</li>
			</ul>

			<strong>Note:</strong>
			If the above assumptions are not valid for your organization, please update item tax templates
			accordingly for your items.
			`
        ),
    });

    d.onhide = () => {
        frappe.xcall(
            "india_compliance.gst_india.utils.disable_item_tax_template_notification"
        );
    };
});
