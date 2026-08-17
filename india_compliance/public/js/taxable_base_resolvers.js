frappe.provide("erpnext");

// Mirror of overrides/taxable_value.py resolvers (client preview).
erpnext.taxable_base_resolvers = erpnext.taxable_base_resolvers || {};

// Item specific tax rate
const _item_rate = (item, tax) => {
    const item_tax_rate = item.item_tax_rate ? JSON.parse(item.item_tax_rate) : {};

    if (tax.account_head in item_tax_rate) return flt(item_tax_rate[tax.account_head]);

    return flt(tax.rate);
};

// Total rate the base is inclusive of (CGST+SGST split = sum of same-charge_type rows).
const _inclusive_rate = (calc, item, tax) => {
    const taxes = (calc.frm && calc.frm.doc.taxes) || [];
    const total = taxes.reduce(
        (s, t) => s + (t.charge_type === tax.charge_type ? _item_rate(item, t) : 0),
        0,
    );
    return total || _item_rate(item, tax);
};

// Tobacco RSP (Rule 31D): tax on RSP-deemed value, report net sale value.
erpnext.taxable_base_resolvers["On MRP"] = (calc, item, tax) => {
    const rate = _inclusive_rate(calc, item, tax);
    const rsp = flt(item.gst_retail_sale_price) * flt(item.qty);
    const deemed = rate ? (rsp * 100) / (100 + rate) : rsp;

    item._dont_update_taxable_value = true;
    item._deemed_taxable_value = deemed * (flt(calc.frm && calc.frm.doc.conversion_rate) || 1);

    return deemed;
};

// Margin scheme (Rule 32(5)), GST inclusive in margin (selling - cost).
// When returning qty < 0, then negative margin is allowed.
erpnext.taxable_base_resolvers["On Margin"] = (calc, item, tax) => {
    const rate = _inclusive_rate(calc, item, tax);
    const cost = flt(item.gst_purchase_price) * flt(item.qty);

    let margin = flt(item.amount) - cost;
    if (margin < 0 && item.qty > 0) margin = 0;

    return rate ? (margin * 100) / (100 + rate) : margin;
};
