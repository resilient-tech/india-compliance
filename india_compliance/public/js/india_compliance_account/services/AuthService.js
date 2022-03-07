export async function get_api_secret() {
    return call_server_method(
        "india_compliance.gst_india.api.get_gst_api_secret"
    );
}

async function set_api_secret(api_secret) {
    return call_server_method(
        "india_compliance.gst_india.api.set_gst_api_secret",
        { api_secret }
    );
}

export async function login(email) {
    const response = await india_compliance.gst_api.call("login", {
        body: { email },
    });

    if (response.message && response.message.session_id) {
        const session = { id: response.message.session_id, email };
        response.session = session;
        set_session(session);
    }

    return response;
}

export function signup(email, gstin) {
    return india_compliance.gst_api.call("signup", {
        body: { email, gstin },
    });
}

export function validateGstin(value) {
    return mockApiCall(true);
}

export function get_session() {
    return call_server_method("india_compliance.gst_india.api.get_session");
}

function set_session(session) {
    call_server_method("india_compliance.gst_india.api.set_session", {
        session,
    });
}

export async function validate_session(session_id) {
    const api_secret = await india_compliance.gst_api
        .call("validate_session", { body: { session_id } })
        .then((response) => response.message && response.message.api_secret);

    if (!api_secret) return;
    await set_api_secret(api_secret);
    return api_secret;
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
