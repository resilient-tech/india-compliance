$(document).on("app_ready", async function () {
    if (!frappe.boot.needs_new_gst_category_notification) return;

    // let other processes finish
    await new Promise(resolve => setTimeout(resolve, 700));
    const d = frappe.msgprint({
        title: __("New GST Category Introduced"),
        indicator: "orange",
        message: __(
            `Dear India Compliance User,
            <br><br>

            We would like to inform you about an important update regarding the GST category for Input Service Distributors (ISD).
            <br><br>

            Previously, <strong>ISD was categorized under Registered Regular</strong> in our system. However, we have now introduced a dedicated GST category <strong>Input Service Distributor</strong> specifically for Input Service Distributors.
            <br><br>

            <strong>Action Required:</strong>
            <br>
            If you have been using the ISD under the <strong>Registered Regular</strong> GST category, please update your records to reflect the new <strong>Input Service Distributor</strong> category.
            `
        ),
    });

    d.onhide = () => {
        frappe.xcall(
            "india_compliance.gst_india.utils.disable_new_gst_category_notification"
        );
    };
});
