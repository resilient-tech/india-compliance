export async function get_subscription_details() {
    return ic.gst_api.call("account.get_subscription_details", {
        method: "GET",
        with_api_secret: true,
    });
}

export async function get_calculator_details() {
    return ic.gst_api.call("account.get_calculator_details", {
        method: "GET",
        with_api_secret: true,
    });
}

export async function create_order(credits, amount) {
    return ic.gst_api.call("account.create_order", {
        method: "POST",
        body: { credits, amount },
        with_api_secret: true,
    });
}
