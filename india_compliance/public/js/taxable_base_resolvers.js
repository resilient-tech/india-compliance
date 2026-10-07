frappe.provide("erpnext");

// Mirror of overrides/taxable_value.py resolvers (client preview).
erpnext.taxable_base_resolvers = erpnext.taxable_base_resolvers || {};

const _item_rate = (item, tax) => {
    const item_tax_rate = item.item_tax_rate ? JSON.parse(item.item_tax_rate) : {};

    if (tax.account_head in item_tax_rate) return flt(item_tax_rate[tax.account_head]);

    return flt(tax.rate);
};

// CGST and SGST rows share one base, so their rates add up
const _inclusive_rate = (calc, item, tax) => {
    const taxes = (calc.frm && calc.frm.doc.taxes) || [];
    const total = taxes.reduce(
        (s, t) => s + (t.charge_type === tax.charge_type ? _item_rate(item, t) : 0),
        0,
    );
    return total || _item_rate(item, tax);
};

// Rule 31D: tax from the MRP, report the net sale value
erpnext.taxable_base_resolvers["On MRP"] = (calc, item, tax) => {
    const conversion_rate = flt(calc.frm && calc.frm.doc.conversion_rate) || 1;
    const rate = _inclusive_rate(calc, item, tax);
    const rsp = (flt(item.gst_retail_sale_price) * flt(item.qty)) / conversion_rate;
    const deemed = rate ? (rsp * 100) / (100 + rate) : rsp;

    item._dont_update_taxable_value = true;
    item._deemed_taxable_value = deemed * conversion_rate;

    return deemed;
};

// Rule 32(5): only the margin is taxed; Rule 35 takes GST out when the price includes it
erpnext.taxable_base_resolvers["On Margin"] = (calc, item, tax) => {
    const conversion_rate = flt(calc.frm && calc.frm.doc.conversion_rate) || 1;
    const cost = (flt(item.gst_purchase_price) * flt(item.qty)) / conversion_rate;

    let margin = flt(item.amount) - cost;
    if (Math.abs(flt(item.amount)) < Math.abs(cost)) margin = 0;

    if (!tax.included_in_print_rate) return margin;

    const rate = _inclusive_rate(calc, item, tax);
    return rate ? (margin * 100) / (100 + rate) : margin;
};
