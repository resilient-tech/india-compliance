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
