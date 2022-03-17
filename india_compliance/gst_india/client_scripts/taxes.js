const SALES_DOCTYPES = [
	"Quotation",
	"Sales Order",
	"Delivery Note",
	"Sales Invoice",
	"POS Invoice",
];

function setup_auto_gst_taxation(doctype) {
	frappe.ui.form.on(doctype, {
		company_address: get_tax_template,
		shipping_address: get_tax_template,
		supplier_address: get_tax_template,
		tax_category: get_tax_template,
		customer_address: get_tax_template,
	});
}

function get_tax_template(frm) {
	if (!frm.doc.company) return;

	let party_details = {
		"shipping_address": frm.doc.shipping_address || "",
		"shipping_address_name": frm.doc.shipping_address_name || "",
		"customer_address": frm.doc.customer_address || "",
		"supplier_address": frm.doc.supplier_address,
		"customer": frm.doc.customer,
		"supplier": frm.doc.supplier,
		"supplier_gstin": frm.doc.supplier_gstin,
		"company_gstin": frm.doc.company_gstin,
		"tax_category": frm.doc.tax_category
	};

	frappe.call({
		method: "india_compliance.gst_india.overrides.transaction.get_regional_address_details",
		args: {
			party_details: JSON.stringify(party_details),
			doctype: frm.doc.doctype,
			company: frm.doc.company
		},
		debounce: 2000,
		callback: function(r) {
			if(r.message) {
				frm.set_value("taxes_and_charges", r.message.taxes_and_charges);
				frm.set_value("taxes", r.message.taxes);
				frm.set_value("place_of_supply", r.message.place_of_supply);
			}
		}
	});
}

function process_gst_category(doctype) {
	let events = {
		refresh: _highlight_gst_category,
		gst_category: _highlight_gst_category,
	};
	const party_type = get_party_type(doctype);
	events[party_type] = function (frm) {
		if (frm.doc.gst_category || frm.doc[`${party_type}_address`]) return;
		update_gst_category(party_type, frm);
	};
	events[`${party_type}_address`] = function (frm) {
		if (frm.doc.gst_category || !frm.doc[party_type]) return;
		update_gst_category(party_type, frm);
	};
	frappe.ui.form.on(doctype, events);
}

function _highlight_gst_category(frm) {
	const party_type = get_party_type(frm.doctype);
	const party_field = frm.fields_dict[party_type];

	if (!frm.doc[party_type] || !frm.doc.gst_category) {
		party_field.set_description("");
		return;
	}

	party_field.set_description(`<em>${frm.doc.gst_category}</em>`);
}
function get_party_type(doctype) {
	return in_list(SALES_DOCTYPES, doctype) ? "customer" : "supplier";
}

function update_gst_category(party_type, frm) {
	frappe.model.get_value(
		frappe.unscrub(party_type),
		frm.doc[party_type],
		"gst_category",
		function (r) {
			frm.set_value("gst_category", r.gst_category);
		}
	);
}
