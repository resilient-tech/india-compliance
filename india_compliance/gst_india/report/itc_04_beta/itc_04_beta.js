// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.query_reports["ITC-04 Beta"] = {
    filters: [
      {
        fieldname: "company",
        label: "Company",
        fieldtype: "Link",
        options: "Company",
      },
      {
        fieldname: "company_gstin",
        label: "Company GSTIN",
        fieldtype: "Data",
      },
      {
        fieldname: "from_date",
        label: "From Date",
        fieldtype: "Date",
      },
      {
        fieldname: "to_date",
        label: "To Date",
        fieldtype: "Date",
      },
      {
        fieldname: "category",
        label: "Invoice Category",
        fieldtype: "Select",
        options: ["", "Table 4", "Table 5A"],
        reqd: 1
      },
    ],
  };
