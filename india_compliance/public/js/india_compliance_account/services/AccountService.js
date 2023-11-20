export async function get_details(type) {
    return india_compliance.gst_api.call(`account.get_${type}_details`, {
        method: "GET",
        with_api_secret: true,
    });
}

export async function update_billing_details(new_billing_details) {
    return india_compliance.gst_api.call("account.update_billing_details", {
        method: "POST",
        body: { new_billing_details },
        with_api_secret: true,
    });
}

export async function create_order(credits, amount) {
    return india_compliance.gst_api.call("account.create_order", {
        method: "POST",
        body: { credits, amount },
        with_api_secret: true,
    });
}

export async function verify_payment(orderId) {
    return india_compliance.gst_api.call("account.verify_payment", {
        method: "POST",
        body: { order_id: orderId },
        with_api_secret: true,
    });
}

export async function get_invoice_history(from_date, to_date) {
    return india_compliance.gst_api.call("account.get_invoice_history", {
        method: "POST",
        body: { from_date, to_date },
        with_api_secret: true,
    });
}

export async function send_invoice_email(invoice_name, email) {
    return india_compliance.gst_api.call("account.send_invoice_email", {
        method: "POST",
        body: { invoice_name, email },
        with_api_secret: true,
    });
}