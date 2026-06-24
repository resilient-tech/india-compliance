frappe.provide("erpnext");

// Mirror of overrides/taxable_value.py resolvers (client preview).
erpnext.taxable_base_resolvers = erpnext.taxable_base_resolvers || {};

// Total rate the base is inclusive of (CGST+SGST split = sum of same-charge_type rows).
const _inclusive_rate = (calc, tax) => {
    const taxes = (calc.frm && calc.frm.doc.taxes) || [];
    const total = taxes.reduce((s, t) => s + (t.charge_type === tax.charge_type ? flt(t.rate) : 0), 0);
    return total || flt(tax.rate);
};

// Tobacco RSP (Rule 31D): tax on RSP-deemed value, report net sale value.
erpnext.taxable_base_resolvers["On MRP"] = (calc, item, tax) => {
    const rate = _inclusive_rate(calc, tax);
    const rsp = flt(item.gst_retail_sale_price) * flt(item.qty);
    const deemed = rate ? (rsp * 100) / (100 + rate) : rsp;

    item._dont_update_taxable_value = true;
    item._deemed_taxable_value = deemed * flt((calc.frm && calc.frm.doc.conversion_rate) || 1);

    return deemed;
};

// Margin scheme (Rule 32(5)), GST inclusive in margin (selling - cost).
erpnext.taxable_base_resolvers["On Margin"] = (calc, item, tax) => {
    const rate = _inclusive_rate(calc, tax);
    const cost = flt(item.gst_purchase_price) * flt(item.qty);
    const margin = Math.max(0, flt(item.amount) - cost);

    return rate ? (margin * 100) / (100 + rate) : margin;
};
