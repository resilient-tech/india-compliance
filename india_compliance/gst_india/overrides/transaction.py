import json
from collections import defaultdict

import frappe
from frappe import _, bold
from frappe.contacts.doctype.address.address import get_default_address
from frappe.model.utils import get_fetch_values
from frappe.utils import cint, flt, format_date
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from erpnext.controllers.taxes_and_totals import (
    get_itemised_tax,
    get_itemised_taxable_amount,
)

from india_compliance.gst_india.constants import (
    GST_RCM_TAX_TYPES,
    GST_TAX_TYPES,
    SALES_DOCTYPES,
    STATE_NUMBERS,
    SUBCONTRACTING_DOCTYPES,
    TAX_TYPES,
)
from india_compliance.gst_india.constants.custom_fields import E_WAYBILL_INV_FIELDS
from india_compliance.gst_india.doctype.gst_settings.gst_settings import (
    restrict_gstr_1_transaction_for,
)
from india_compliance.gst_india.doctype.gstin.gstin import get_and_validate_gstin_status
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_account_gst_tax_type_map,
    get_gst_accounts_by_type,
    get_hsn_settings,
    get_place_of_supply,
    get_place_of_supply_options,
    is_overseas_doc,
    join_list_with_custom_separators,
    validate_gst_category,
    validate_gstin,
)
from india_compliance.gst_india.utils.gstr_1 import SUPECOM
from india_compliance.income_tax_india.overrides.tax_withholding_category import (
    get_tax_withholding_accounts,
)

DOCTYPES_WITH_GST_DETAIL = {
    "Supplier Quotation",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Quotation",
    "Sales Order",
    "Delivery Note",
    "Sales Invoice",
    "POS Invoice",
}


def set_gst_breakup(doc):
    gst_breakup_html = frappe.render_template(
        "templates/gst_breakup.html", dict(doc=doc)
    )
    if not gst_breakup_html:
        return

    doc.gst_breakup_table = gst_breakup_html.replace("\n", "").replace("    ", "")


def update_taxable_values(doc):

    if doc.doctype not in DOCTYPES_WITH_GST_DETAIL:
        return

    total_charges = 0
    apportioned_charges = 0
    tax_witholding_amount = 0

    if doc.taxes:
        if any(
            row for row in doc.taxes if row.tax_amount and row.gst_tax_type in TAX_TYPES
        ):
            reference_row_index = next(
                (
                    cint(row.row_id) - 1
                    for row in doc.taxes
                    if row.tax_amount
                    and row.charge_type == "On Previous Row Total"
                    and row.gst_tax_type in TAX_TYPES
                ),
                None,  # ignore accounts after GST accounts
            )

        else:
            # If no GST account is used
            reference_row_index = -1
            tax_witholding_amount = get_tds_amount(doc)

        if reference_row_index is not None:
            total_charges = (
                doc.taxes[reference_row_index].base_total
                - doc.base_net_total
                - tax_witholding_amount
            )

    # base net total may be zero if invoice has zero rated items + shipping
    total_value = doc.base_net_total if doc.base_net_total else doc.total_qty

    if not total_value:
        return

    for item in doc.items:
        item.taxable_value = item.base_net_amount

        if not total_charges:
            continue

        proportionate_value = item.base_net_amount if doc.base_net_total else item.qty

        applicable_charges = flt(
            proportionate_value * (total_charges / total_value),
            item.precision("taxable_value"),
        )

        item.taxable_value += applicable_charges
        apportioned_charges += applicable_charges

    if apportioned_charges != total_charges:
        item.taxable_value += total_charges - apportioned_charges


def validate_item_wise_tax_detail(doc):
    if doc.doctype not in DOCTYPES_WITH_GST_DETAIL:
        return

    item_taxable_values = defaultdict(float)
    item_qty_map = defaultdict(float)

    for row in doc.items:
        item_key = row.item_code or row.item_name
        item_taxable_values[item_key] += row.taxable_value
        item_qty_map[item_key] += row.qty

    for row in doc.taxes:
        if not row.gst_tax_type:
            continue

        if row.charge_type != "Actual":
            continue

        item_wise_tax_detail = frappe.parse_json(row.item_wise_tax_detail or "{}")

        for item_name, (tax_rate, tax_amount) in item_wise_tax_detail.items():
            if tax_amount and not tax_rate:
                frappe.throw(
                    _(
                        "Tax Row #{0}: Charge Type is set to Actual. However, this would"
                        " not compute item taxes, and your further reporting will be affected."
                    ).format(row.idx),
                    title=_("Invalid Charge Type"),
                )

            # Sales Invoice is created with manual tax amount. So, when a sales return is created,
            # the tax amount is not recalculated, causing the issue.

            is_cess_non_advol = (
                row.gst_tax_type and "cess_non_advol" in row.gst_tax_type
            )
            multiplier = (
                item_qty_map.get(item_name, 0)
                if is_cess_non_advol
                else item_taxable_values.get(item_name, 0) / 100
            )
            tax_difference = abs(multiplier * tax_rate - tax_amount)

            if tax_difference > 1:
                correct_charge_type = (
                    "On Item Quantity" if is_cess_non_advol else "On Net Total"
                )

                frappe.throw(
                    _(
                        "Tax Row #{0}: Charge Type is set to Actual. However, Tax Amount {1} as computed for Item {2}"
                        " is incorrect. Try setting the Charge Type to {3}"
                    ).format(row.idx, tax_amount, bold(item_name), correct_charge_type)
                )


def get_tds_amount(doc):
    tds_accounts = get_tax_withholding_accounts(doc.company)
    tds_amount = 0
    for row in doc.taxes:
        if row.account_head not in tds_accounts:
            continue

        if row.get("add_deduct_tax") and row.add_deduct_tax == "Deduct":
            tds_amount -= row.base_tax_amount_after_discount_amount

        else:
            tds_amount += row.base_tax_amount_after_discount_amount

    return tds_amount


def is_indian_registered_company(doc):
    if not doc.get("company_gstin"):
        country, gst_category = frappe.get_cached_value(
            "Company", doc.company, ("country", "gst_category")
        )

        if country != "India" or gst_category == "Unregistered":
            return False

    return True


def validate_mandatory_fields(doc, fields, error_message=None, throw=True):
    if isinstance(fields, str):
        fields = (fields,)

    if not error_message:
        error_message = _("{0} is a mandatory field for GST Transactions")

    for field in fields:
        if doc.get(field):
            continue

        if doc.flags.ignore_mandatory:
            return False

        if not throw:
            return False

        frappe.throw(
            error_message.format(bold(_(doc.meta.get_label(field)))),
            title=_("Missing Required Field"),
        )


def get_applicable_gst_accounts(
    company, *, for_sales, is_inter_state, is_reverse_charge=False
):
    all_gst_accounts = set()
    applicable_gst_accounts = set()

    if for_sales:
        account_types = ["Output"]
        reverse_charge_type = "Sales Reverse Charge"
    else:
        account_types = ["Input"]
        reverse_charge_type = "Purchase Reverse Charge"

    if is_reverse_charge:
        account_types.append(reverse_charge_type)

    for account_type in account_types:
        accounts = get_gst_accounts_by_type(company, account_type, throw=True)

        if not accounts:
            continue

        for account_type, account_name in accounts.items():
            if not account_name:
                continue

            if is_inter_state and account_type in ["cgst_account", "sgst_account"]:
                all_gst_accounts.add(account_name)
                continue

            if not is_inter_state and account_type == "igst_account":
                all_gst_accounts.add(account_name)
                continue

            applicable_gst_accounts.add(account_name)
            all_gst_accounts.add(account_name)

    return all_gst_accounts, applicable_gst_accounts


def get_valid_accounts(company, *, for_sales=False, for_purchase=False, throw=True):
    all_valid_accounts = []
    intra_state_accounts = []
    inter_state_accounts = []

    account_types = []
    if for_sales:
        account_types.extend(["Output", "Sales Reverse Charge"])

    if for_purchase:
        account_types.extend(["Input", "Purchase Reverse Charge"])

    for account_type in account_types:
        accounts = get_gst_accounts_by_type(company, account_type, throw=throw)
        if not accounts:
            continue

        all_valid_accounts.extend(accounts.values())
        intra_state_accounts.append(accounts.cgst_account)
        intra_state_accounts.append(accounts.sgst_account)
        inter_state_accounts.append(accounts.igst_account)

    return all_valid_accounts, intra_state_accounts, inter_state_accounts


def set_gst_tax_type(doc, method=None):
    if not doc.taxes:
        return

    gst_tax_account_map = get_gst_account_gst_tax_type_map()

    for tax in doc.taxes:
        # Setting as None if not GST Account
        tax.gst_tax_type = gst_tax_account_map.get(tax.account_head)


class GSTAccounts:
    def validate(self, doc, is_sales_transaction=False):
        self.doc = doc
        self.is_sales_transaction = is_sales_transaction

        if not self.doc.taxes:
            return

        if not self.has_gst_tax_rows():
            return

        self.setup_defaults()

        self.validate_invalid_account_for_transaction()  # Sales / Purchase
        self.validate_for_same_party_gstin()
        self.validate_reverse_charge_accounts()
        self.validate_sales_transaction()
        self.validate_purchase_transaction()
        self.validate_for_invalid_account_type()  # CGST / SGST / IGST
        self.validate_for_charge_type()
        self.validate_missing_accounts_in_item_tax_template()

    def setup_defaults(self):
        (
            self.all_valid_accounts,
            self.intra_state_accounts,
            self.inter_state_accounts,
        ) = get_valid_accounts(
            self.doc.company,
            for_sales=self.is_sales_transaction,
            for_purchase=not self.is_sales_transaction,
            throw=False,
        )

        self.first_gst_idx = self._get_matched_idx(self.gst_tax_rows, TAX_TYPES)
        self.used_accounts = set(row.account_head for row in self.gst_tax_rows)

    def has_gst_tax_rows(self):
        self.gst_tax_rows = [
            row for row in self.doc.taxes if row.tax_amount and row.gst_tax_type
        ]

        return self.gst_tax_rows

    def validate_invalid_account_for_transaction(self):
        """
        - Only Valid Accounts should be allowed.
        eg: Output accounts not allowed in Purchase Invoice
        """
        for row in self.gst_tax_rows:
            if row.account_head in self.all_valid_accounts:
                continue

            self._throw(
                _(
                    "Row #{0}: {1} is not a valid GST account for this transaction"
                ).format(row.idx, bold(row.account_head))
            )

    def validate_for_same_party_gstin(self):
        party_gstin = (
            self.doc.billing_address_gstin
            if self.is_sales_transaction
            else self.doc.supplier_gstin
        )

        if not party_gstin or self.doc.company_gstin != party_gstin:
            return

        self._throw(
            _(
                "Cannot charge GST in Row #{0} since Company GSTIN and Party GSTIN are"
                " same"
            ).format(self.first_gst_idx)
        )

    def validate_reverse_charge_accounts(self):
        """
        - RCM accounts should not be used in transactions without Reverse Charge
        """
        if self.doc.doctype == "Payment Entry" or self.doc.get("is_reverse_charge"):
            return

        if idx := self._get_matched_idx(self.gst_tax_rows, GST_RCM_TAX_TYPES):
            self._throw(
                _(
                    "Cannot use Reverse Charge Account in Row #{0} since transaction is"
                    " without Reverse Charge"
                ).format(idx)
            )

    def validate_sales_transaction(self):
        if not self.is_sales_transaction:
            return

        if is_export_without_payment_of_gst(self.doc):
            self._throw(
                _(
                    "Cannot charge GST in Row #{0} since export is without payment of GST"
                ).format(self.first_gst_idx)
            )

    def validate_purchase_transaction(self):
        if self.is_sales_transaction:
            return

        if self.doc.gst_category == "Registered Composition":
            self._throw(
                _(
                    "Cannot claim Input GST in Row #{0} since purchase is being made from a"
                    " dealer registered under Composition Scheme"
                ).format(self.first_gst_idx)
            )

        if not self.doc.is_reverse_charge and not self.doc.supplier_gstin:
            self._throw(
                _(
                    "Cannot charge GST in Row #{0} since purchase is from a Supplier"
                    " without GSTIN"
                ).format(self.first_gst_idx)
            )

    def validate_for_invalid_account_type(self):
        """
        - SEZ / Inter-State supplies should not have CGST or SGST account
        - Intra-State supplies should not have IGST account
        - If Intra-State, ensure both CGST and SGST accounts are used
        """
        if self.is_sales_transaction:
            company_address_field = "company_address"
        elif self.doc.doctype == "Stock Entry":
            company_address_field = "bill_from_address"
        else:
            company_address_field = "billing_address"

        company_gst_category = frappe.db.get_value(
            "Address", self.doc.get(company_address_field), "gst_category"
        )

        if company_gst_category == "SEZ":
            return

        is_inter_state = is_inter_state_supply(self.doc)

        for row in self.gst_tax_rows:
            if is_inter_state:
                if row.account_head in self.intra_state_accounts:
                    self._throw(
                        _(
                            "Row #{0}: Cannot charge CGST/SGST for inter-state supplies"
                        ).format(row.idx)
                    )

            elif row.account_head in self.inter_state_accounts:
                self._throw(
                    _("Row #{0}: Cannot charge IGST for intra-state supplies").format(
                        row.idx
                    )
                )

        if is_inter_state:
            return

        if self.used_accounts and not set(self.intra_state_accounts[:2]).issubset(
            self.used_accounts
        ):
            self._throw(
                _(
                    "Cannot use only one of CGST or SGST account for intra-state"
                    " supplies"
                )
            )

    def validate_for_charge_type(self):
        previous_row_references = set()
        for row in self.gst_tax_rows:
            if row.charge_type == "On Previous Row Amount":
                self._throw(
                    _(
                        "Row #{0}: Charge Type cannot be <strong>On Previous Row"
                        " Amount</strong> for a GST Account"
                    ).format(row.idx),
                    title=_("Invalid Charge Type"),
                )

            if row.charge_type == "On Previous Row Total":
                previous_row_references.add(row.row_id)

            # validating charge type "On Item Quantity" and non_cess_advol_account
            self.validate_charge_type_for_cess_non_advol_accounts(row)

        if len(previous_row_references) > 1:
            self._throw(
                _(
                    "Only one row can be selected as a Reference Row for GST Accounts with"
                    " Charge Type <strong>On Previous Row Total</strong>"
                ),
                title=_("Invalid Reference Row"),
            )

    @staticmethod
    def validate_charge_type_for_cess_non_advol_accounts(tax_row):
        if not tax_row.gst_tax_type:
            return

        if (
            tax_row.charge_type == "On Item Quantity"
            and "cess_non_advol" not in tax_row.gst_tax_type
        ):
            frappe.throw(
                _(
                    "Row #{0}: Charge Type cannot be <strong>On Item Quantity</strong>"
                    " as it is not a Cess Non Advol Account"
                ).format(tax_row.idx),
                title=_("Invalid Charge Type"),
            )

        if (
            tax_row.charge_type not in ["On Item Quantity", "Actual"]
            and "cess_non_advol" in tax_row.gst_tax_type
        ):
            frappe.throw(
                _(
                    "Row #{0}: Charge Type must be <strong>On Item Quantity / Actual</strong>"
                    " as it is a Cess Non Advol Account"
                ).format(tax_row.idx),
                title=_("Invalid Charge Type"),
            )

    def validate_missing_accounts_in_item_tax_template(self):
        for row in self.doc.get("items") or []:
            if not row.item_tax_template:
                continue

            for account in self.used_accounts:
                if account in row.item_tax_rate:
                    continue

                frappe.msgprint(
                    _(
                        "Item Row #{0}: GST Account {1} is missing in Item Tax Template {2}"
                    ).format(row.idx, bold(account), bold(row.item_tax_template)),
                    title=_("Invalid Item Tax Template"),
                    indicator="orange",
                )

    def _get_matched_idx(self, rows_to_search, tax_types):
        return next(
            (row.idx for row in rows_to_search if row.gst_tax_type in tax_types), None
        )

    def _throw(self, message, title=None):
        frappe.throw(message, title=title or _("Invalid GST Account"))


def validate_tax_accounts_for_non_gst(doc):
    """GST Tax Accounts should not be charged for Non GST Items"""
    accounts_list = get_all_gst_accounts(doc.company)

    for row in doc.taxes:
        if row.account_head in accounts_list and row.tax_amount:
            frappe.throw(
                _("Row #{0}: Cannot charge GST for Non GST Items").format(
                    row.idx, row.account_head
                ),
                title=_("Invalid Taxes"),
            )


def validate_items(doc, throw):
    """Validate Items for a GST Compliant Invoice"""

    if not doc.get("items"):
        return

    item_tax_templates = frappe._dict()
    items_with_duplicate_taxes = []
    non_gst_items = []
    has_gst_items = False

    for row in doc.items:
        # Collect data to validate that non-GST items are not used with GST items
        if row.gst_treatment == "Non-GST":
            non_gst_items.append(row.idx)
            continue

        has_gst_items = True

        # Different Item Tax Templates should not be used for the same Item Code
        if row.item_code not in item_tax_templates:
            item_tax_templates[row.item_code] = row.item_tax_template
            continue

        if row.item_tax_template != item_tax_templates[row.item_code]:
            items_with_duplicate_taxes.append(bold(row.item_code))

    if not has_gst_items:
        update_taxable_values(doc)
        validate_tax_accounts_for_non_gst(doc)

        return False

    if non_gst_items:
        if not throw:
            return False
        frappe.throw(
            _(
                "Items not covered under GST cannot be clubbed with items for which GST"
                " is applicable. Please create another document for items in the"
                " following row numbers:<br>{0}"
            ).format(", ".join(bold(row_no) for row_no in non_gst_items)),
            title=_("Invalid Items"),
        )

    if items_with_duplicate_taxes:
        if not throw:
            return False
        frappe.throw(
            _(
                "Cannot use different Item Tax Templates in different rows for"
                " following items:<br> {0}"
            ).format("<br>".join(items_with_duplicate_taxes)),
            title="Inconsistent Item Tax Templates",
        )

    return True


def validate_place_of_supply(doc):
    valid_options = get_place_of_supply_options(
        as_list=True,
    )

    if doc.place_of_supply not in valid_options:
        frappe.throw(
            _(
                '"<strong>{0}</strong>" is not a valid Place of Supply. Please choose'
                " from available options."
            ).format(doc.place_of_supply),
            title=_("Invalid Place of Supply"),
        )

    if (
        doc.doctype in SALES_DOCTYPES
        and doc.gst_category == "Overseas"
        and doc.place_of_supply != "96-Other Countries"
        and (
            not doc.shipping_address_name
            or frappe.db.get_value("Address", doc.shipping_address_name, "country")
            != "India"
        )
    ):
        frappe.throw(
            _(
                "GST Category is set to <strong>Overseas</strong> but Place of Supply"
                " is within India. Shipping Address in India is required for classifing"
                " this as B2C."
            ),
            title=_("Invalid Shipping Address"),
        )


def is_inter_state_supply(doc):
    gst_category = (
        doc.bill_to_gst_category if doc.doctype == "Stock Entry" else doc.gst_category
    )

    return gst_category == "SEZ" or (
        doc.place_of_supply[:2] != get_source_state_code(doc)
    )


def get_source_state_code(doc):
    """
    Get the state code of the state from which goods / services are being supplied.
    Logic opposite to that of utils.get_place_of_supply
    """

    if doc.doctype in SALES_DOCTYPES or doc.doctype == "Payment Entry":
        return doc.company_gstin[:2]

    if doc.doctype == "Stock Entry":
        return doc.bill_from_gstin[:2]

    if doc.gst_category == "Overseas":
        return "96"

    if doc.gst_category == "Unregistered" and doc.supplier_address:
        return frappe.db.get_value(
            "Address",
            doc.supplier_address,
            "gst_state_number",
        )

    # for purchase, subcontracting order and receipt
    return (doc.supplier_gstin or doc.company_gstin)[:2]


def validate_backdated_transaction(doc, gst_settings=None, action="create"):
    if gstr_1_filed_upto := restrict_gstr_1_transaction_for(
        doc.posting_date, doc.company_gstin, gst_settings
    ):
        frappe.throw(
            _(
                "You are not allowed to {0} {1} as GSTR-1 has been filed upto {2}"
            ).format(action, doc.doctype, frappe.bold(format_date(gstr_1_filed_upto))),
            title=_("Restricted Changes"),
        )


def validate_hsn_codes(doc):
    validate_hsn_code, valid_hsn_length = get_hsn_settings()

    if not validate_hsn_code:
        return

    return _validate_hsn_codes(doc, valid_hsn_length, message=None)


def validate_sales_reverse_charge(doc):
    if doc.get("is_reverse_charge") and not doc.billing_address_gstin:
        frappe.throw(
            _(
                "Transaction cannot be reverse charge since sales is to customer"
                " without GSTIN"
            )
        )


def _validate_hsn_codes(doc, valid_hsn_length, message=None):
    rows_with_missing_hsn = []
    rows_with_invalid_hsn = []

    for item in doc.items:
        if not (hsn_code := item.get("gst_hsn_code")):
            rows_with_missing_hsn.append(str(item.idx))

        elif len(hsn_code) not in valid_hsn_length:
            rows_with_invalid_hsn.append(str(item.idx))

    if doc.docstatus == 1:
        # Same error for erroneous rows on submit
        rows_with_invalid_hsn += rows_with_missing_hsn

        if not rows_with_invalid_hsn:
            return

        frappe.throw(
            _(
                "{0}"
                "Please enter a valid HSN/SAC code for the following row numbers:"
                " <br>{1}"
            ).format(message or "", frappe.bold(", ".join(rows_with_invalid_hsn))),
            title=_("Invalid HSN/SAC"),
        )

    if rows_with_missing_hsn:
        frappe.msgprint(
            _(
                "{0}" "Please enter HSN/SAC code for the following row numbers: <br>{1}"
            ).format(message or "", frappe.bold(", ".join(rows_with_missing_hsn))),
            title=_("Invalid HSN/SAC"),
        )

    if rows_with_invalid_hsn:
        frappe.msgprint(
            _(
                "{0}"
                "HSN/SAC code should be {1} digits long for the following"
                " row numbers: <br>{2}"
            ).format(
                message or "",
                join_list_with_custom_separators(valid_hsn_length),
                frappe.bold(", ".join(rows_with_invalid_hsn)),
            ),
            title=_("Invalid HSN/SAC"),
        )


def validate_overseas_gst_category(doc):
    if not is_overseas_doc(doc):
        return

    overseas_enabled = frappe.get_cached_value(
        "GST Settings", "GST Settings", "enable_overseas_transactions"
    )

    if not overseas_enabled:
        frappe.throw(
            _(
                "GST Category cannot be set to {0} since it is disabled in GST Settings"
            ).format(frappe.bold(doc.gst_category))
        )

    if doc.doctype == "POS Invoice":
        frappe.throw(_("Cannot set GST Category to SEZ / Overseas in POS Invoice"))


# DEPRECATED IN v16
def get_itemised_tax_breakup_header(item_doctype, tax_accounts):
    if is_hsn_wise_breakup_needed(item_doctype):
        return [_("HSN/SAC"), _("Taxable Amount")] + tax_accounts
    else:
        return [_("Item"), _("Taxable Amount")] + tax_accounts


def get_itemised_tax_breakup_data(doc):
    itemised_tax = get_itemised_tax(doc.taxes)
    taxable_amounts = get_itemised_taxable_amount(doc.items)

    if is_hsn_wise_breakup_needed(doc.doctype + " Item"):
        return get_hsn_wise_breakup(doc, itemised_tax, taxable_amounts)

    return get_item_wise_breakup(itemised_tax, taxable_amounts)


def get_item_wise_breakup(itemised_tax, taxable_amounts):
    itemised_tax_data = []
    for item_code, taxes in itemised_tax.items():
        itemised_tax_data.append(
            frappe._dict(
                {
                    "item": item_code,
                    "taxable_amount": taxable_amounts.get(item_code),
                    **taxes,
                }
            )
        )

    return itemised_tax_data


def get_hsn_wise_breakup(doc, itemised_tax, taxable_amounts):
    hsn_tax_data = frappe._dict()
    considered_items = set()
    for item in doc.items:
        item_code = item.item_code or item.item_name
        if item_code in considered_items:
            continue

        hsn_code = item.gst_hsn_code
        tax_row = itemised_tax.get(item_code, {})
        tax_rate = next(iter(tax_row.values()), {}).get("tax_rate", 0)

        hsn_tax = hsn_tax_data.setdefault(
            (hsn_code, tax_rate),
            frappe._dict({"item": hsn_code, "taxable_amount": 0}),
        )

        hsn_tax.taxable_amount += taxable_amounts.get(item_code, 0)
        for tax_account, tax_details in tax_row.items():
            hsn_tax.setdefault(
                tax_account, frappe._dict({"tax_rate": 0, "tax_amount": 0})
            )
            hsn_tax[tax_account].tax_rate = tax_details.get("tax_rate")
            hsn_tax[tax_account].tax_amount += tax_details.get("tax_amount")

        considered_items.add(item_code)

    return list(hsn_tax_data.values())


def is_hsn_wise_breakup_needed(doctype):
    if frappe.get_meta(doctype).has_field("gst_hsn_code") and frappe.get_cached_value(
        "GST Settings", None, "hsn_wise_tax_breakup"
    ):
        return True


def get_regional_round_off_accounts(company, account_list):
    country = frappe.get_cached_value("Company", company, "country")
    if country != "India" or not frappe.get_cached_value(
        "GST Settings", "GST Settings", "round_off_gst_values"
    ):
        return account_list

    if isinstance(account_list, str):
        account_list = json.loads(account_list)

    account_list.extend(get_all_gst_accounts(company))

    return account_list


def update_party_details(party_details, doctype, company):
    party_details.update(
        get_gst_details(party_details, doctype, company, update_place_of_supply=True)
    )


@frappe.whitelist()
def get_party_details_for_subcontracting(party_details, doctype, company):
    party_details = frappe.parse_json(party_details)

    party_address_field = (
        "supplier_address" if doctype != "Stock Entry" else "bill_to_address"
    )
    party_details[party_address_field] = get_default_address(
        "Supplier", party_details.supplier
    )
    party_details.update(
        get_fetch_values(
            doctype, party_address_field, party_details[party_address_field]
        )
    )

    return party_details.update(
        {
            **get_gst_details(
                party_details, doctype, company, update_place_of_supply=True
            ),
        }
    )


@frappe.whitelist()
def get_gst_details(party_details, doctype, company, *, update_place_of_supply=False):
    """
    This function does not check for permissions since it returns insensitive data
    based on already sensitive input (party details)

    Data returned:
     - place of supply (based on address name in party_details)
     - tax template
     - taxes in the tax template
    """

    is_sales_transaction = doctype in SALES_DOCTYPES or doctype == "Payment Entry"
    party_details = frappe.parse_json(party_details)
    gst_details = frappe._dict()

    # Party/Address Defaults
    if is_sales_transaction:
        company_gstin_field = "company_gstin"
        party_gstin_field = "billing_address_gstin"
        party_address_field = "customer_address"
        gst_category_field = "gst_category"

    elif doctype == "Stock Entry":
        company_gstin_field = "bill_from_gstin"
        party_gstin_field = "bill_to_gstin"
        party_address_field = "bill_to_address"
        gst_category_field = "bill_to_gst_category"

    else:
        company_gstin_field = "company_gstin"
        party_gstin_field = "supplier_gstin"
        party_address_field = "supplier_address"
        gst_category_field = "gst_category"

    if not party_details.get(party_address_field):
        party_gst_details = get_party_gst_details(
            party_details, is_sales_transaction, party_gstin_field
        )

        # updating party details to get correct place of supply
        if party_gst_details:
            party_details.update(party_gst_details)
            gst_details.update(party_gst_details)

    # POS
    gst_details.place_of_supply = (
        party_details.place_of_supply
        if (not update_place_of_supply and party_details.place_of_supply)
        else get_place_of_supply(party_details, doctype)
    )

    # set is_reverse_charge as per party_gst_details if not set
    if not is_sales_transaction and "is_reverse_charge" not in party_details:
        is_reverse_charge = frappe.db.get_value(
            "Supplier",
            party_details.supplier,
            "is_reverse_charge_applicable as is_reverse_charge",
            as_dict=True,
        )

        if is_reverse_charge:
            party_details.update(is_reverse_charge)
            gst_details.update(is_reverse_charge)

    if doctype == "Payment Entry":
        return gst_details

    # Taxes Not Applicable
    if (
        (
            party_details.get(company_gstin_field)
            and party_details.get(company_gstin_field)
            == party_details.get(party_gstin_field)
        )  # Internal transfer
        or (is_sales_transaction and is_export_without_payment_of_gst(party_details))
        or (
            not is_sales_transaction
            and (
                party_details.get(gst_category_field) == "Registered Composition"
                or (
                    not party_details.is_reverse_charge
                    and not party_details.get(party_gstin_field)
                )
            )
        )
    ):
        # GST Not Applicable
        gst_details.taxes_and_charges = ""
        gst_details.taxes = []
        return gst_details

    master_doctype = (
        "Sales Taxes and Charges Template"
        if is_sales_transaction or doctype in SUBCONTRACTING_DOCTYPES
        else "Purchase Taxes and Charges Template"
    )

    # Tax Category in Transaction
    tax_template_by_category = get_tax_template_based_on_category(
        master_doctype, company, party_details
    )

    if tax_template_by_category:
        gst_details.taxes_and_charges = tax_template_by_category
        gst_details.taxes = get_taxes_and_charges(
            master_doctype, tax_template_by_category
        )
        return gst_details

    if not gst_details.place_of_supply or not party_details.get(company_gstin_field):
        return gst_details

    # Fetch template by perceived tax
    if default_tax := get_tax_template(
        master_doctype,
        company,
        is_inter_state_supply(
            party_details.copy().update(
                doctype=doctype, place_of_supply=gst_details.place_of_supply
            ),
        ),
        party_details.get(company_gstin_field)[:2],
        party_details.is_reverse_charge,
    ):
        gst_details.taxes_and_charges = default_tax
        gst_details.taxes = get_taxes_and_charges(master_doctype, default_tax)

    return gst_details


def get_party_gst_details(party_details, is_sales_transaction, gstin_fieldname):
    """fetch GSTIN and GST category from party"""

    party_type = "Customer" if is_sales_transaction else "Supplier"

    if not (party := party_details.get(party_type.lower())) or not isinstance(
        party, str
    ):
        return

    return frappe.db.get_value(
        party_type,
        party,
        ("gst_category", f"gstin as {gstin_fieldname}"),
        as_dict=True,
    )


def get_tax_template_based_on_category(master_doctype, company, party_details):
    if not party_details.tax_category:
        return

    default_tax = frappe.db.get_value(
        master_doctype,
        {"company": company, "tax_category": party_details.tax_category},
        "name",
    )

    return default_tax


def get_tax_template(
    master_doctype, company, is_inter_state, state_code, is_reverse_charge
):
    tax_categories = frappe.get_all(
        "Tax Category",
        fields=["name", "is_inter_state", "gst_state"],
        filters={
            "is_inter_state": 1 if is_inter_state else 0,
            "is_reverse_charge": 1 if is_reverse_charge else 0,
            "disabled": 0,
        },
    )

    default_tax = ""

    for tax_category in tax_categories:
        if STATE_NUMBERS.get(tax_category.gst_state) == state_code or (
            not default_tax and not tax_category.gst_state
        ):
            default_tax = frappe.db.get_value(
                master_doctype,
                {"company": company, "disabled": 0, "tax_category": tax_category.name},
                "name",
            )
    return default_tax


def validate_reverse_charge_transaction(doc):
    base_gst_tax = 0
    base_reverse_charge_booked = 0

    if not doc.get("is_reverse_charge"):
        return

    is_return = doc.get("is_return", False)

    def _throw_tax_error(is_positive, tax, comment_suffix=""):
        expected = "positive" if is_positive else "negative"
        if is_return:
            expected = "negative" if is_positive else "positive"

        frappe.throw(
            _("Row #{0}: Tax amount should be {1} for GST Account {2}{3}").format(
                tax.idx, expected, tax.account_head, comment_suffix
            )
        )

    for tax in doc.get("taxes"):
        if not tax.gst_tax_type or not tax.tax_amount:
            continue

        tax_amount = tax.base_tax_amount_after_discount_amount
        if is_return:
            tax_amount = -tax_amount

        is_positive = tax_amount > 0

        if "rcm" not in tax.gst_tax_type:
            # NON RCM logic
            if tax.get("add_deduct_tax", "Add") != "Add" or not is_positive:
                _throw_tax_error(True, tax)

            base_gst_tax += tax_amount

        elif "rcm" in tax.gst_tax_type:
            # RCM logic
            if tax.get("add_deduct_tax") == "Deduct":
                if not is_positive:
                    _throw_tax_error(True, tax, " as you are Deducting Tax")

                base_reverse_charge_booked -= tax_amount

            else:
                if is_positive:
                    _throw_tax_error(False, tax)

                base_reverse_charge_booked += tax_amount

    condition = flt(base_gst_tax + base_reverse_charge_booked, 2) == 0

    if not condition:
        msg = _("Booked reverse charge is not equal to applied tax amount")
        msg += "<br>"
        msg += _(
            "Please refer {gst_document_link} to learn more about how to setup and"
            " create reverse charge invoice"
        ).format(
            gst_document_link=(
                '<a href="https://docs.erpnext.com/docs/user/manual/en/regional/india/gst-setup">GST'
                " Documentation</a>"
            )
        )

        frappe.throw(msg)


def is_export_without_payment_of_gst(doc):
    return is_overseas_doc(doc) and not doc.is_export_with_gst


class ItemGSTDetails:
    FIELDMAP = {}

    def get(self, docs, doctype, company):
        """
        Return Item GST Details for a list of documents
        """
        self.get_item_defaults()
        self.set_tax_amount_precisions(doctype)

        response = frappe._dict()

        for doc in docs:
            self.doc = doc
            if not doc.get("items") or not doc.get("taxes"):
                continue

            self.set_item_wise_tax_details()

            for item in doc.get("items"):
                response[item.name] = self.get_item_tax_detail(item)

        return response

    def update(self, doc):
        """
        Update Item GST Details for a single document
        """
        self.doc = doc
        if not self.doc.get("items"):
            return

        self.get_item_defaults()
        self.set_tax_amount_precisions(doc.doctype)
        self.set_item_wise_tax_details()
        self.update_item_tax_details()

    def get_item_defaults(self):
        item_defaults = frappe._dict(count=0)

        for row in GST_TAX_TYPES:
            item_defaults[f"{row}_rate"] = 0
            item_defaults[f"{row}_amount"] = 0

        self.item_defaults = item_defaults

    def set_item_wise_tax_details(self):
        """
        Item Tax Details complied
        Example:
        {
            "Item Code 1": {
                "count": 2,
                "cgst_rate": 9,
                "cgst_amount": 18,
                "sgst_rate": 9,
                "sgst_amount": 18,
                ...
            },
            ...
        }

        Possible Exceptions Handled:
        - There could be more than one row for same account
        - Item count added to handle rounding errors
        """

        tax_details = frappe._dict()

        for row in self.doc.get("items"):
            key = row.item_code or row.item_name
            if key not in tax_details:
                tax_details[key] = self.item_defaults.copy()
            tax_details[key]["count"] += 1

        for row in self.doc.taxes:
            if (
                not row.base_tax_amount_after_discount_amount
                or row.gst_tax_type not in GST_TAX_TYPES
                or not row.item_wise_tax_detail
            ):
                continue

            tax = row.gst_tax_type
            tax_rate_field = f"{tax}_rate"
            tax_amount_field = f"{tax}_amount"

            old = json.loads(row.item_wise_tax_detail)

            tax_difference = row.base_tax_amount_after_discount_amount
            last_item_with_tax = None

            # update item taxes
            for item_name in old:
                if item_name not in tax_details:
                    # Do not compute if Item is not present in Item table
                    # There can be difference in Item Table and Item Wise Tax Details
                    continue

                item_taxes = tax_details[item_name]
                tax_rate, tax_amount = old[item_name]

                tax_difference -= tax_amount

                # cases when charge type == "Actual"
                if tax_amount and not tax_rate:
                    continue

                item_taxes[tax_rate_field] = tax_rate
                item_taxes[tax_amount_field] += tax_amount

                # update tax difference only for taxable items
                if tax_amount:
                    last_item_with_tax = item_taxes

            # Floating point errors
            tax_difference = flt(tax_difference, 5)

            # Handle rounding errors
            if tax_difference and last_item_with_tax:
                last_item_with_tax[tax_amount_field] += tax_difference

        self.item_tax_details = tax_details

    def update_item_tax_details(self):
        for item in self.doc.get("items"):
            item.update(self.get_item_tax_detail(item))

    def get_item_key(self, item):
        return item.item_code or item.item_name

    def get_item_tax_detail(self, item):
        """
        - get item_tax_detail as it is if
            - only one row exists for same item
            - it is the last item

        - If count is greater than 1,
            - Manually calculate tax_amount for item
            - Reduce item_tax_detail with
                - tax_amount
                - count
        """
        item_key = self.get_item_key(item)

        item_tax_detail = self.item_tax_details.get(item_key)
        if not item_tax_detail:
            return {}

        if item_tax_detail.count == 1:
            return item_tax_detail

        item_tax_detail["count"] -= 1

        # Handle rounding errors
        response = item_tax_detail.copy()
        for tax in GST_TAX_TYPES:
            if (tax_rate := item_tax_detail[f"{tax}_rate"]) == 0:
                continue

            tax_amount_field = f"{tax}_amount"
            precision = self.precision.get(tax_amount_field)

            multiplier = (
                item.qty if tax == "cess_non_advol" else item.taxable_value / 100
            )
            tax_amount = flt(tax_rate * multiplier, precision)

            item_tax_detail[tax_amount_field] -= tax_amount

            response.update({tax_amount_field: tax_amount})

        return response

    def set_tax_amount_precisions(self, doctype):
        item_doctype = frappe.get_meta(doctype).get_field("items").options

        meta = frappe.get_meta(item_doctype)

        self.precision = frappe._dict()
        default_precision = cint(frappe.db.get_default("float_precision")) or 3

        for tax_type in GST_TAX_TYPES:
            fieldname = f"{tax_type}_amount"
            field = meta.get_field(fieldname)
            if not field:
                continue

            self.precision[fieldname] = field.precision or default_precision


class ItemGSTTreatment:
    def set(self, doc):
        self.doc = doc
        is_sales_transaction = doc.doctype in SALES_DOCTYPES

        if is_sales_transaction and is_overseas_doc(doc):
            self.set_for_overseas()
            return

        has_gst_accounts = any(row.gst_tax_type in TAX_TYPES for row in self.doc.taxes)

        if not has_gst_accounts:
            self.set_for_no_taxes()
            return

        self.update_gst_treatment_map()
        self.set_default_treatment()

    def set_for_overseas(self):
        for item in self.doc.items:
            item.gst_treatment = "Zero-Rated"

    def set_for_no_taxes(self):
        for item in self.doc.items:
            if item.gst_treatment not in ("Exempted", "Non-GST"):
                item.gst_treatment = "Nil-Rated"

    def update_gst_treatment_map(self):
        item_templates = set()
        gst_treatments = set()
        gst_treatment_map = {}

        for item in self.doc.items:
            item_templates.add(item.item_tax_template)
            gst_treatments.add(item.gst_treatment)

        if any(
            gst_treatment in gst_treatments
            for gst_treatment in ["Zero-Rated", "Nil-Rated"]
        ):
            # doc changed from overseas to local sale post
            # taxes added after save
            _gst_treatments = frappe.get_all(
                "Item Tax Template",
                filters={"name": ("in", item_templates)},
                fields=["name", "gst_treatment"],
            )
            gst_treatment_map = {row.name: row.gst_treatment for row in _gst_treatments}

        self.gst_treatment_map = gst_treatment_map

    def set_default_treatment(self):
        default_treatment = self.get_default_treatment()

        for item in self.doc.items:
            if item.gst_treatment in ("Zero-Rated", "Nil-Rated"):
                item.gst_treatment = self.gst_treatment_map.get(item.item_tax_template)

            if not item.gst_treatment or not item.item_tax_template:
                item.gst_treatment = default_treatment

    def get_default_treatment(self):
        default = "Taxable"

        for row in self.doc.taxes:
            if row.charge_type in ("Actual", "On Item Quantity"):
                continue

            if row.gst_tax_type not in GST_TAX_TYPES:
                continue

            if row.rate == 0:
                default = "Nil-Rated"

            break

        return default


def set_reverse_charge_as_per_gst_settings(doc):
    if doc.doctype in SALES_DOCTYPES:
        return

    gst_settings = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("enable_rcm_for_unregistered_supplier", "rcm_threshold"),
        as_dict=1,
    )

    if (
        not gst_settings.enable_rcm_for_unregistered_supplier
        or not doc.gst_category == "Unregistered"
        or (doc.grand_total and doc.grand_total <= gst_settings.rcm_threshold)
        or doc.get("is_opening") == "Yes"
    ):
        return

    set_reverse_charge(doc)


def set_reverse_charge(doc):
    doc.is_reverse_charge = 1
    is_inter_state = is_inter_state_supply(doc)

    # get defaults
    default_tax = get_tax_template(
        "Purchase Taxes and Charges Template",
        doc.company,
        is_inter_state,
        doc.company_gstin[:2],
        doc.is_reverse_charge,
    )

    if not default_tax:
        return

    template = (
        get_taxes_and_charges("Purchase Taxes and Charges Template", default_tax) or []
    )

    # compare accounts
    all_gst_accounts, applicable_gst_accounts = get_applicable_gst_accounts(
        doc.company,
        for_sales=False,
        is_inter_state=is_inter_state,
        is_reverse_charge=True,
    )
    existing_accounts = set(
        row.account_head for row in doc.taxes if row.account_head in all_gst_accounts
    )
    has_invalid_accounts = existing_accounts - applicable_gst_accounts

    if has_invalid_accounts:
        return

    has_same_accounts = not (applicable_gst_accounts - existing_accounts)

    # update taxes
    if doc.taxes_and_charges == default_tax and has_same_accounts:
        return

    doc.taxes_and_charges = default_tax
    doc.set("taxes", template)


def validate_gstin_status(gstin, transaction_date):
    settings = frappe.get_cached_doc("GST Settings")
    if not settings.validate_gstin_status:
        return

    get_and_validate_gstin_status(gstin, transaction_date)


def validate_gst_transporter_id(doc):
    if not doc.get("gst_transporter_id"):
        return

    doc.gst_transporter_id = validate_gstin(
        doc.gst_transporter_id, label="GST Transporter ID", is_transporter_id=True
    )


def validate_company_address_field(doc):
    if doc.doctype not in DOCTYPES_WITH_GST_DETAIL:
        return

    company_address_field = "company_address"
    if doc.doctype not in SALES_DOCTYPES:
        company_address_field = "billing_address"

    if (
        validate_mandatory_fields(
            doc,
            company_address_field,
            _(
                "Please set {0} to ensure Company GSTIN is fetched in the transaction."
            ).format(bold(doc.meta.get_label(company_address_field))),
        )
        is False
    ):
        return False


def before_validate_transaction(doc, method=None):
    if ignore_gst_validations(doc, throw=False):
        return False

    if not doc.place_of_supply:
        doc.place_of_supply = get_place_of_supply(doc, doc.doctype)

    set_reverse_charge_as_per_gst_settings(doc)


def validate_transaction(doc, method=None):
    if ignore_gst_validations(doc):
        return False

    if doc.place_of_supply:
        validate_place_of_supply(doc)
    else:
        doc.place_of_supply = get_place_of_supply(doc, doc.doctype)

    if validate_company_address_field(doc) is False:
        return False

    if validate_mandatory_fields(doc, ("company_gstin", "place_of_supply")) is False:
        return False

    # Ignore validation for Quotation not to Customer
    if doc.doctype != "Quotation" or doc.quotation_to == "Customer":
        if (
            validate_mandatory_fields(
                doc,
                "gst_category",
                _(
                    "{0} is a mandatory field for GST Transactions. Please ensure that"
                    " it is set in the Party and / or Address."
                ),
            )
            is False
        ):
            return False

    elif not doc.gst_category:
        doc.gst_category = "Unregistered"

    validate_overseas_gst_category(doc)

    if is_sales_transaction := doc.doctype in SALES_DOCTYPES:
        validate_hsn_codes(doc)
        validate_sales_reverse_charge(doc)
        gstin = doc.billing_address_gstin
    elif doc.doctype == "Payment Entry":
        is_sales_transaction = True
        gstin = doc.billing_address_gstin
    else:
        gstin = doc.supplier_gstin

    validate_gstin_status(gstin, doc.get("posting_date") or doc.get("transaction_date"))
    validate_gst_transporter_id(doc)
    validate_ecommerce_gstin(doc)

    validate_gst_category(doc.gst_category, gstin)

    GSTAccounts().validate(doc, is_sales_transaction)
    validate_reverse_charge_transaction(doc)
    update_taxable_values(doc)
    validate_item_wise_tax_detail(doc)


def before_print(doc, method=None, print_settings=None):
    if (
        ignore_gst_validations(doc, throw=False)
        or not doc.place_of_supply
        or not doc.company_gstin
    ):
        return

    set_ecommerce_supply_type(doc)
    set_gst_breakup(doc)


def onload(doc, method=None):

    if (
        ignore_gst_validations(doc, throw=False)
        or not doc.place_of_supply
        or not doc.company_gstin
    ):
        return

    set_ecommerce_supply_type(doc)
    set_gst_breakup(doc)


def validate_ecommerce_gstin(doc):
    if not doc.get("ecommerce_gstin"):
        return

    doc.ecommerce_gstin = validate_gstin(
        doc.ecommerce_gstin, label="E-commerce GSTIN", is_tcs_gstin=True
    )


def update_gst_details(doc, method=None):
    if doc.doctype in DOCTYPES_WITH_GST_DETAIL:
        ItemGSTDetails().update(doc)

    ItemGSTTreatment().set(doc)


def after_mapping(target_doc, method=None, source_doc=None):
    # Copy e-Waybill fields only from DN to SI
    if not source_doc or source_doc.doctype not in (
        "Delivery Note",
        "Purchase Receipt",
    ):
        return

    for field in E_WAYBILL_INV_FIELDS:
        fieldname = field.get("fieldname")
        target_doc.set(fieldname, source_doc.get(fieldname))


def ignore_gst_validations(doc, throw=True):
    if (
        not is_indian_registered_company(doc)
        or doc.get("is_opening") == "Yes"
        # If there are no GST items, then no need to proceed further
        # Also returning if item with multiple taxes
        or validate_items(doc, throw) is False
    ):
        return True


def on_change_item(doc, method=None):
    """
    Objective:
    Child item is saved before trying to update parent doc.
    Hence we can't verify has_value_changed for items in the parent doc.

    Solution:
    - Set a flag in on_change of item
    - Runs for both insert and save (update after submit)
    - Set flag only if `ignore_validate_update_after_submit` is set

    Reference:
    erpnext.controllers.accounts_controller.update_child_qty_rate
    """
    if doc.flags.ignore_validate_update_after_submit:
        frappe.flags.through_update_item = True


def before_update_after_submit(doc, method=None):
    if not frappe.flags.through_update_item:
        return

    if ignore_gst_validations(doc):
        return

    if is_sales_transaction := doc.doctype in SALES_DOCTYPES:
        validate_hsn_codes(doc)

    GSTAccounts().validate(doc, is_sales_transaction)
    update_taxable_values(doc)
    validate_item_wise_tax_detail(doc)
    update_gst_details(doc)


def set_ecommerce_supply_type(doc):
    """
    - Set GSTR-1 E-commerce section for virtual field ecommerce_supply_type
    """
    if doc.doctype not in ("Sales Order", "Sales Invoice", "Delivery Note"):
        return

    if not doc.ecommerce_gstin:
        return

    if doc.is_reverse_charge:
        doc.ecommerce_supply_type = SUPECOM.US_9_5.value
    else:
        doc.ecommerce_supply_type = SUPECOM.US_52.value
