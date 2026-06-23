frappe.provide("erpnext");

// GST on MRP — base = price list rate * qty. Mirrors server on_mrp (overrides/taxable_value.py).
erpnext.taxable_base_resolvers = erpnext.taxable_base_resolvers || {};
erpnext.taxable_base_resolvers["On MRP"] = (calc, item, tax) => flt(item.price_list_rate) * flt(item.qty);
