frappe.provide("frappe.help.help_links");

const docsUrl = "https://docs.indiacompliance.app/docs/";
const blogUrl = "https://docs.indiacompliance.app/blog/";

//India Compliance Account
frappe.help.help_links["india-compliance-account"] = [
    {
        label: "India Compliance Account",
        url: docsUrl + "getting-started/india_compliance_account",
    },
];

//GST Settings
frappe.help.help_links["Form/GST Settings"] = [
    {
        label: "Setting Up GST accounts",
        url: docsUrl + "configuration/gst_setup#gst-accounts"
    },
    {
        label: "Setting Up API",
        url: docsUrl + "ewaybill-and-einvoice/gst_settings"
    },
];

//Company
frappe.help.help_links["Form/Company"] = [
    {
        label: "Print Settings",
        url: docsUrl + "configuration/gst_setup#print-format",
    }
];


//Doctypes
//Sales Invoice
if (!frappe.help.help_links["Form/Sales Invoice"]) {
    frappe.help.help_links["Form/Sales Invoice"] = [];
}

frappe.help.help_links["Form/Sales Invoice"].push(
    {
        label: "e-Waybill",
        url: docsUrl + "ewaybill-and-einvoice/generating_e_waybill",
    },
    {
        label: "e-Invoice",
        url: docsUrl + "ewaybill-and-einvoice/generating_e_invoice",
    },
);

//Stock Entry
frappe.help.help_links["Form/Stock Entry"].push({
    label: "Subcontracting Workflow",
    url: blogUrl + "posts/post5",
})

//Subcontracting Receipt
frappe.help.help_links["Form/Subcontracting Receipt"] = [
    {
        label: "Subcontracting Workflow",
        url: blogUrl + "posts/post5",
    },
    {
        label: "GST Job Work Stock Movement report",
        url: docsUrl + "gst-reports/miscellaneous_reports#gst-job-work-stock-movement-report",
    },
]

//Journal Entry
frappe.help.help_links["Form/Journal Entry"] = [
    {
        label: "Reversal of Input Tax Credit",
        url: docsUrl + "configuration/other_transaction#reversal-of-input-tax-credit",
    }
]

// GST Reports
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


//Query Reports
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

//Purchase Reconciliation
frappe.help.help_links["Form/Purchase Reconciliation Tool"] = [
    {
        label: "Reconciling Purchase",
        url: docsUrl + "purchase-reconciliation/reconciling_purchase",
    },
];

//Miscellaneous
frappe.help.help_links["query-report/Audit Trail"] = [
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