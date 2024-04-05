frappe.provide("india_compliance");

india_compliance.set_gstin_options = async function (frm) {
	const { query, params } = india_compliance.get_gstin_query(frm.doc.company);
	const { message } = await frappe.call({
		method: query,
		args: params,
	});

	if (!message) return [];
	const gstin_field = frm.get_field("company_gstin");
	gstin_field.set_data(message);
	return message;
}
