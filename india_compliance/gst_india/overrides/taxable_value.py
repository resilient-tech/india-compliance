import frappe
from frappe.utils import flt

from india_compliance.gst_india.constants import TAX_TYPES


def get_item_taxable_value(doc, item, default):
    # reset: the same item is resolved again on every save
    item._dont_update_taxable_value = False
    item._deemed_taxable_value = None

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

        # a resolver may tax a deemed base but report the net value (MRP)
        if getattr(item, "_dont_update_taxable_value", None):
            return default

        return base * flt(doc.get("conversion_rate") or 1)

    return default


def _item_rate(item, tax):
    item_tax_rate = frappe.parse_json(item.get("item_tax_rate")) or {}

    if tax.get("account_head") in item_tax_rate:
        return flt(item_tax_rate[tax.account_head])

    return flt(tax.get("rate"))


def _inclusive_rate(doc, item, tax):
    # CGST and SGST rows share one base, so their rates add up
    rates = [_item_rate(item, t) for t in doc.get("taxes") or [] if t.charge_type == tax.charge_type]
    return sum(rates) or _item_rate(item, tax)


# Rule 31D: tax from the MRP, report the net sale value
def on_mrp(calc, item, tax):
    conversion_rate = flt(calc.doc.get("conversion_rate")) or 1
    rate = _inclusive_rate(calc.doc, item, tax)
    rsp = flt(item.get("gst_retail_sale_price")) * flt(item.qty) / conversion_rate
    deemed = rsp * 100 / (100 + rate) if rate else rsp

    item._dont_update_taxable_value = True
    item._deemed_taxable_value = deemed * conversion_rate

    return deemed


# Rule 32(5): only the margin is taxed; Rule 35 takes GST out when the price includes it
def on_margin(calc, item, tax):
    conversion_rate = flt(calc.doc.get("conversion_rate")) or 1
    cost = flt(item.get("gst_purchase_price")) * flt(item.qty) / conversion_rate
    margin = flt(item.amount) - cost
    if abs(flt(item.amount)) < abs(cost):
        margin = 0

    if not tax.get("included_in_print_rate"):
        return margin

    rate = _inclusive_rate(calc.doc, item, tax)
    return margin * 100 / (100 + rate) if rate else margin
