export async function get_api_secret() {
    return call_server_method(
        "india_compliance.gst_india.page.india_compliance_account.get_api_secret"
    );
}

export async function set_api_secret(api_secret) {
    return call_server_method(
        "india_compliance.gst_india.page.india_compliance_account.set_api_secret",
        { api_secret }
    );
}

export function login(email) {
    return india_compliance.gst_api.call("auth/login", {
        body: { email },
        fail_silently: true,
    });
}

export function signup(email, gstin) {
    return india_compliance.gst_api.call("auth/signup", {
        body: { email, gstin },
        fail_silently: true,
    });
}

export function check_free_trial_eligibility(gstin) {
    return india_compliance.gst_api.call("auth/is_eligible_for_free_trial", {
        body: { gstin },
        fail_silently: true,
    });
}

export function get_session() {
    return call_server_method("india_compliance.gst_india.page.india_compliance_account.get_auth_session");
}

export function set_session(session) {
    call_server_method("india_compliance.gst_india.page.india_compliance_account.set_auth_session", {
        session,
    });
}

export function validate_session(session_id) {
    return india_compliance.gst_api.call("auth/validate_session", {
        body: { session_id },
    });
}

function call_server_method(method, args) {
    return frappe
        .call({
            method: method,
            args: args,
            silent: true,
        })
        .then((response) => response.message || null)
        .catch(() => null);
}
