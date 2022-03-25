export async function get_subscription_details() {
    return ic.gst_api.call("account/get_subscription_details", {
        method: "GET",
        with_api_secret: true,
    });
}
