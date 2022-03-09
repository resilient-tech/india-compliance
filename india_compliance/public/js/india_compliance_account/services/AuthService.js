export async function get_api_secret() {
    return call_server_method(
        "india_compliance.gst_india.api.get_gst_api_secret"
    );
}

export async function set_api_secret(api_secret) {
    return call_server_method(
        "india_compliance.gst_india.api.set_gst_api_secret",
        { api_secret }
    );
}

export function login(email) {
    return india_compliance.gst_api.call("auth/login", {
        body: { email },
    });
}

export function signup(email, gstin) {
    return india_compliance.gst_api.call("auth/signup", {
        body: { email, gstin },
    });
}

export function validateGstin(value) {
    return mockApiCall(true);
}

export function get_session() {
    return call_server_method("india_compliance.gst_india.api.get_session");
}

export function set_session(session) {
    call_server_method("india_compliance.gst_india.api.set_session", {
        session,
    });
}

export function validate_session(session_id) {
    return india_compliance.gst_api.call("auth/validate_session", {
        body: { session_id },
        fail_silently: true,
    });
}

function mockApiCall(response = {}, seconds = 1) {
    return new Promise((resolve) => {
        setTimeout(() => {
            resolve(response);
        }, 1000 * seconds);
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
