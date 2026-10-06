"""Per-item GST taxable value (assessable value reported in returns).

Defaults to net amount. A custom charge_type with a resolver registered under ERPNext's
``erpnext_taxable_base_resolvers`` can decouple the *tax base* (what the rate applies to)
from the *reported taxable value*. The resolver returns the base and stamps transient flags:

  RSP (Rule 31D, "On MRP"): tax on RSP-deemed value, report the net sale value.
  Margin (Rule 32(5), "On Margin"): tax on margin, balance reported as other charges.
"""

import frappe
from frappe.utils import flt

from india_compliance.gst_india.constants import TAX_TYPES


def get_item_taxable_value(doc, item, default):
    """Resolved base of the first GST resolver row, else default.

    Honours ``_dont_update_taxable_value`` (resolver wants the net default, e.g. RSP).
    First resolver row wins; qty-based cess_non_advol has no resolver.
    """
    # clear up front so a stale value from a prior pass
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

        if getattr(item, "_dont_update_taxable_value", None):
            return default

        return base * flt(doc.get("conversion_rate") or 1)

    return default


def _item_rate(item, tax):
    "Item specific tax rate"
    item_tax_rate = frappe.parse_json(item.get("item_tax_rate")) or {}

    if tax.get("account_head") in item_tax_rate:
        return flt(item_tax_rate[tax.account_head])

    return flt(tax.get("rate"))


def _inclusive_rate(doc, item, tax):
    rates = [_item_rate(item, t) for t in doc.get("taxes") or [] if t.charge_type == tax.charge_type]
    return sum(rates) or _item_rate(item, tax)


def on_mrp(calc, item, tax):
    """Tobacco RSP, Rule 31D. RSP is tax-inclusive: tax = RSP*rate/(100+rate), deemed
    assessable = RSP*100/(100+rate). Tax adds on top of the net sale value, which is what's
    reported — so flag report-as-net and hand validation the deemed base.

    RSP from the user-entered `gst_retail_sale_price` (company currency); no fallback.
    """
    conversion_rate = flt(calc.doc.get("conversion_rate")) or 1
    rate = _inclusive_rate(calc.doc, item, tax)
    rsp = flt(item.get("gst_retail_sale_price")) * flt(item.qty) / conversion_rate
    deemed = rsp * 100 / (100 + rate) if rate else rsp

    item._dont_update_taxable_value = True
    item._deemed_taxable_value = deemed * conversion_rate

    return deemed


def on_margin(calc, item, tax):
    """Second-hand margin scheme, Rule 32(5). Only the margin (selling - cost) is taxable,
    reported as taxable value (tax == rate*taxable holds). When the tax row is inclusive,
    Rule 35 takes the GST out: deemed = margin*100/(100+rate). Selling below cost -> 0
    (no GST), on a sale or its return.

    Cost from the user-entered `gst_purchase_price` (company currency); no fallback.
    """
    conversion_rate = flt(calc.doc.get("conversion_rate")) or 1
    cost = flt(item.get("gst_purchase_price")) * flt(item.qty) / conversion_rate
    margin = flt(item.amount) - cost
    if abs(flt(item.amount)) < abs(cost):
        margin = 0

    if not tax.get("included_in_print_rate"):
        return margin

    rate = _inclusive_rate(calc.doc, item, tax)
    return margin * 100 / (100 + rate) if rate else margin
