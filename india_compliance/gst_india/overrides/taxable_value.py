"""Per-item GST taxable value — the base GST is charged on.

Defaults to the item net amount. A custom ``charge_type`` whose resolver is registered
under ERPNext's ``erpnext_taxable_base_resolvers`` overrides it (e.g. GST on MRP); IC reads
the same hook, so every GST figure (per-item CGST/SGST/IGST, e-Invoice, e-Waybill, GSTR)
follows that base.
"""

import frappe
from frappe.utils import flt

from india_compliance.gst_india.constants import TAX_TYPES


def get_item_taxable_value(doc, item, default):
    """Resolved base for the first GST row whose charge_type has a resolver, else default.

    One assessable value per item, so the first resolver row wins; a qty-based
    cess_non_advol row has no resolver and is skipped.
    """
    resolvers = frappe.get_hooks("erpnext_taxable_base_resolvers") or {}
    if not resolvers:
        return default

    for tax in doc.get("taxes") or []:
        if tax.get("gst_tax_type") not in TAX_TYPES:
            continue

        path = resolvers.get(tax.charge_type)
        if not path:
            continue

        method = path[-1] if isinstance(path, list | tuple) else path
        base = flt(frappe.get_attr(method)(frappe._dict(doc=doc), item, tax))
        # taxable_value is company currency
        return base * flt(doc.get("conversion_rate") or 1)

    return default


def on_mrp(calc, item, tax):
    """Example resolver: GST on MRP (price list rate), not the net amount."""
    return flt(item.price_list_rate) * flt(item.qty)
