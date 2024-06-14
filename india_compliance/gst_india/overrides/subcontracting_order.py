from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    update_gst_details,
)
from india_compliance.gst_india.overrides.ineligible_itc import update_valuation_rate
from india_compliance.gst_india.utils.taxes_controller import (
    set_item_wise_tax_rates,
    set_taxable_value,
    set_total_taxes,
    validate_taxes,
)


def before_save(doc, method=None):
    update_gst_details(doc)


def before_submit(doc, method=None):
    update_gst_details(doc)


def validate(doc, method=None):
    # This has to be called after `amount` is updated based upon `additional_costs` in erpnext
    set_taxable_value(doc)
    set_taxes_and_totals(doc)

    validate_taxes(doc)
    update_valuation_rate(doc)


def set_taxes_and_totals(doc):
    set_item_wise_tax_rates(doc)
    set_total_taxes(doc)
