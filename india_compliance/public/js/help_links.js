frappe.provide("frappe.help.help_links");

const docsUrl = "https://docs.indiacompliance.app/docs/";

frappe.help.help_links["india-compliance-account"] = [
	{
		label: "India Compliance Account",
		url: docsUrl + "getting-started/india_compliance_account",
	},
];

if (!frappe.help.help_links["Form/Sales Invoice"]) {
	frappe.help.help_links["Form/Sales Invoice"] = [];
}

frappe.help.help_links["Form/Sales Invoice"].push({
	label: "Sales Transaction",
	url: docsUrl + "configuration/sales_transaction",
});

frappe.help.help_links["List/Sales Invoice"].push({
	label: "Sales Transaction",
	url: docsUrl + "configuration/sales_transaction",
});

frappe.help.help_links["Form/Purchase Invoice"] = [
	{
		label: "Purchase Transaction",
		url: docsUrl + "configuration/purchase_transaction",
	},
	{
		label: "e-Waybill",
		url: docsUrl + "ewaybill-and-einvoice/generating_e_waybill",
	}
]

frappe.help.help_links["List/Purchase Invoice"].push({
	label: "Purchase Transaction",
	url: docsUrl + "configuration/purchase_transaction",
})

frappe.help.help_links["Form/GSTR-1 Beta"] = [
	{
		label: "GSTR-1 Beta",
		url: docsUrl + "gst-reports/gstr1",
	},
];

frappe.help.help_links["Form/GSTR 3B Report"] = [
	{
		label: "GSTR 3B Report",
		url: docsUrl + "gst-reports/gstr3b",
	},
];

frappe.help.help_links["List/GSTR 3B Report"] = [
	{
		label: "GSTR 3B Report",
		url: docsUrl + "gst-reports/gstr3b",
	},
];

frappe.help.help_links["query-report/GST Job Work Stock Movement"] = [
	{
		label: "GST Job Work Stock Movement",
		url: docsUrl + "gst-reports/miscellaneous_reports#gst-job-work-stock-movement-report",
	},
];

frappe.help.help_links["query-report/GST Balance"] = [
	{
		label: "GST Balance",
		url: docsUrl + "gst-reports/miscellaneous_reports#gst-balance-report",
	},
];

frappe.help.help_links["query-report/GST Sales Register Beta"] = [
	{
		label: "GST Sales Register Beta",
		url: docsUrl + "gst-reports/miscellaneous_reports#gst-sales-register-beta-report",
	},
];

frappe.help.help_links["query-report/GST Purchase Register"] = [
	{
		label: "GST Purchase Register",
		url: docsUrl + "gst-reports/miscellaneous_reports#gst-purchase-register-beta-report",
	},
];

frappe.help.help_links["Form/Purchase Reconciliation Tool"] = [
	{
		label: "Setup Purchase Reconciliation Tool",
		url: docsUrl + "purchase-reconciliation/purchase_reconciliation_setup",
	},
	{
		label: "Reconciling Purchase",
		url: docsUrl + "purchase-reconciliation/reconciling_purchase",
	},
	{
		label: "Auto Reconcile",
		url: docsUrl + "purchase-reconciliation/auto_reconcile",
	},
];

frappe.help.help_links["Form/Audit Trail"] = [
	{
		label: "Audit Trail",
		url: docsUrl + "miscellaneous/audit_trail",
	},
];

frappe.help.help_links["Form/Lower Deduction Certificate"] = [
	{
		label: "Lower Deduction Certificate",
		url: docsUrl + "miscellaneous/lower_deduction_certificate",
	},
];