# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.query_builder.functions import IfNull, Sum
from frappe.utils import today
from erpnext.accounts.general_ledger import make_gl_entries, make_reverse_gl_entries
from erpnext.controllers.accounts_controller import AccountsController
from erpnext.stock.get_item_details import _get_item_tax_template

from india_compliance.gst_india.overrides.ineligible_itc import (
    update_landed_cost_voucher_for_gst_expense,
    update_regional_gl_entries,
    update_valuation_rate,
)
from india_compliance.gst_india.overrides.transaction import (
    GSTAccounts,
    set_gst_tax_type,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.gst_india.utils.taxes_controller import (
    CustomTaxController,
    update_gst_details,
)


class BillofEntry(Document):
    get_gl_dict = AccountsController.get_gl_dict
    get_value_in_transaction_currency = (
        AccountsController.get_value_in_transaction_currency
    )
    get_voucher_subtype = AccountsController.get_voucher_subtype
    company_currency = AccountsController.company_currency

    def onload(self):
        if self.docstatus != 1:
            return

        self.set_onload(
            "journal_entry_exists",
            frappe.db.exists(
                "Journal Entry Account",
                {
                    "reference_type": "Bill of Entry",
                    "reference_name": self.name,
                    "docstatus": 1,
                },
            ),
        )

    def before_validate(self):
        self.set_taxes_and_totals()

    def before_submit(self):
        self.validate_qty()

    def validate(self):
        set_gst_tax_type(self)
        self.validate_purchase_invoice()
        self.validate_taxes()
        self.reconciliation_status = "Unreconciled"
        update_gst_details(self)
        update_valuation_rate(self)

    def on_submit(self):
        gl_entries = self.get_gl_entries()
        update_regional_gl_entries(gl_entries, self)
        make_gl_entries(gl_entries)
        self.update_pending_boe_qty()

    def on_cancel(self):
        self.ignore_linked_doctypes = ("GL Entry",)
        make_reverse_gl_entries(voucher_type=self.doctype, voucher_no=self.name)
        self.update_pending_boe_qty()

        frappe.db.set_value(
            "GST Inward Supply",
            {"link_doctype": "Bill of Entry", "link_name": self.name},
            {
                "match_status": "",
                "link_name": "",
                "link_doctype": "",
                "action": "No Action",
            },
        )

    # Code adapted from AccountsController.on_trash
    def on_trash(self):
        if not frappe.db.get_single_value(
            "Accounts Settings", "delete_linked_ledger_entries"
        ):
            return

        frappe.db.delete(
            "GL Entry", {"voucher_type": self.doctype, "voucher_no": self.name}
        )

    def set_defaults(self):
        self.set_item_defaults()
        self.set_default_accounts()

    def set_item_defaults(self):
        """These defaults are needed for taxes and totals to get calculated"""
        for item in self.items:
            item.name = frappe.generate_hash(length=10)
            item.customs_duty = 0

    def set_default_accounts(self):
        company = frappe.get_cached_doc("Company", self.company)
        self.customs_expense_account = company.default_customs_expense_account
        self.customs_payable_account = company.default_customs_payable_account

    def set_taxes_and_totals(self):
        self.validate_item_tax_template()
        self.taxes_controller = CustomTaxController(self)

        self.taxes_controller.set_item_wise_tax_rates()
        self.calculate_totals()

    def calculate_totals(self):
        self.set_total_customs_and_taxable_values()
        self.taxes_controller.update_tax_amount()
        self.total_amount_payable = self.total_customs_duty + self.total_taxes

    def set_total_customs_and_taxable_values(self):
        total_customs_duty = 0
        total_taxable_value = 0

        for item in self.items:
            item.taxable_value = item.assessable_value + item.customs_duty
            total_customs_duty += item.customs_duty
            total_taxable_value += item.taxable_value

        self.total_customs_duty = total_customs_duty
        self.total_taxable_value = total_taxable_value

    def validate_purchase_invoice(self):
        pi_names = {row.purchase_invoice for row in self.items}
        purchase_invoices = frappe.get_all(
            "Purchase Invoice",
            filters={"name": ["in", pi_names]},
            fields=["docstatus", "gst_category", "name", "company", "company_gstin"],
        )

        for invoice in purchase_invoices:
            if invoice.company != self.company:
                frappe.throw(
                    _("Company for Purchase Invoice {0} must be {1}").format(
                        invoice.name, self.company
                    )
                )

            if invoice.company_gstin != self.company_gstin:
                frappe.throw(
                    _("Company GSTIN for Purchase Invoice {0} must be {1}").format(
                        invoice.name, self.company_gstin
                    )
                )

            if invoice.docstatus != 1:
                frappe.throw(
                    _(
                        "Purchase Invoice {0} must be submitted when creating a Bill of Entry"
                    ).format(invoice.name)
                )

            if invoice.gst_category != "Overseas":
                frappe.throw(
                    _(
                        "GST Category must be set to Overseas in Purchase Invoice {0} to create"
                        " a Bill of Entry"
                    ).format(invoice.name)
                )

        pi_item_names = frappe.get_all(
            "Purchase Invoice Item",
            filters={"parent": ["in", pi_names]},
            pluck="name",
        )

        for item in self.items:
            if not item.pi_detail:
                frappe.throw(
                    _("Row #{0}: Purchase Invoice Item is required").format(item.idx)
                )

            if item.pi_detail not in pi_item_names:
                frappe.throw(
                    _(
                        "Row #{0}: Purchase Invoice Item {1} not found in Purchase"
                        " Invoice {2}"
                    ).format(
                        item.idx,
                        frappe.bold(item.pi_detail),
                        frappe.bold(item.purchase_invoice),
                    )
                )

    def validate_taxes(self):
        input_accounts = get_gst_accounts_by_type(self.company, "Input", throw=True)

        for tax in self.taxes:
            if not tax.tax_amount:
                continue

            if tax.account_head not in (
                input_accounts.igst_account,
                input_accounts.cess_account,
                input_accounts.cess_non_advol_account,
            ):
                frappe.throw(
                    _(
                        "Row #{0}: Only Input IGST and CESS accounts are allowed in"
                        " Bill of Entry"
                    ).format(tax.idx)
                )

            GSTAccounts.validate_charge_type_for_cess_non_advol_accounts(tax)

            if tax.charge_type != "Actual":
                continue

            item_wise_tax_rates = json.loads(tax.item_wise_tax_rates)
            if not item_wise_tax_rates:
                frappe.throw(
                    _(
                        "Tax Row #{0}: Charge Type is set to Actual. However, this would"
                        " not compute item taxes, and your further reporting will be affected."
                    ).format(tax.idx),
                    title=_("Invalid Charge Type"),
                )

            taxable_value_map = {}
            item_qty_map = {}

            for row in self.get("items"):
                taxable_value_map[row.name] = row.taxable_value
                item_qty_map[row.name] = row.qty

            # validating total tax
            total_tax = 0
            is_non_cess_advol = tax.gst_tax_type == "cess_non_advol"

            for item, rate in item_wise_tax_rates.items():
                multiplier = (
                    item_qty_map.get(item, 0)
                    if is_non_cess_advol
                    else taxable_value_map.get(item, 0) / 100
                )
                total_tax += multiplier * rate

            tax_difference = abs(total_tax - tax.tax_amount)

            if tax_difference > 1:
                column = "On Item Quantity" if is_non_cess_advol else "On Net Total"
                frappe.throw(
                    _(
                        "Tax Row #{0}: Charge Type is set to Actual. However, Tax Amount {1}"
                        " is incorrect. Try setting the Charge Type to {2}."
                    ).format(row.idx, tax.tax_amount, column)
                )

    def validate_item_tax_template(self):
        for item in self.items:
            if item.item_code and item.get("item_tax_template"):
                item_doc = frappe.get_cached_doc("Item", item.item_code)
                args = {
                    "net_rate": item.get("taxable_value"),
                    "base_net_rate": item.get("taxable_value"),
                    "tax_category": self.get("tax_category"),
                    "bill_date": self.bill_of_entry_date,
                    "company": self.get("company"),
                }

                item_group = item_doc.item_group
                item_group_taxes = []

                while item_group:
                    item_group_doc = frappe.get_cached_doc("Item Group", item_group)
                    item_group_taxes += item_group_doc.taxes or []
                    item_group = item_group_doc.parent_item_group

                item_taxes = item_doc.taxes or []

                if not item_group_taxes and (not item_taxes):
                    # No validation if no taxes in item or item group
                    continue

                taxes = _get_item_tax_template(
                    args, item_taxes + item_group_taxes, for_validate=True
                )

                if taxes:
                    if item.item_tax_template not in taxes:
                        item.item_tax_template = taxes[0]
                        frappe.msgprint(
                            _(
                                "Row {0}: Item Tax template updated as per validity and rate applied"
                            ).format(item.idx, frappe.bold(item.item_code))
                        )

    def get_gl_entries(self):
        gl_entries = []
        remarks = "No Remarks"

        for item in self.items:
            gl_entries.append(
                self.get_gl_dict(
                    {
                        "account": self.customs_expense_account,
                        "debit": item.customs_duty,
                        "credit": 0,
                        "cost_center": item.cost_center,
                        "project": item.project,
                        "remarks": remarks,
                    },
                    item=item,
                )
            )

        for tax in self.taxes:
            gl_entries.append(
                self.get_gl_dict(
                    {
                        "account": tax.account_head,
                        "debit": tax.tax_amount,
                        "credit": 0,
                        "cost_center": self.cost_center,
                        "remarks": remarks,
                    },
                )
            )

        gl_entries.append(
            self.get_gl_dict(
                {
                    "account": self.customs_payable_account,
                    "debit": 0,
                    "credit": self.total_amount_payable,
                    "cost_center": self.cost_center,
                    "remarks": remarks,
                },
            )
        )

        return gl_entries

    # Overriding AccountsController method
    def validate_account_currency(self, account, account_currency=None):
        if account_currency == "INR":
            return

        frappe.throw(
            _("Row #{0}: Account {1} must be of INR currency").format(
                self.idx, frappe.bold(account)
            )
        )

    def get_stock_items(self):
        stock_items = []
        item_codes = list(set(item.item_code for item in self.get("items")))
        if item_codes:
            stock_items = frappe.db.get_values(
                "Item",
                {"name": ["in", item_codes], "is_stock_item": 1},
                pluck="name",
                cache=True,
            )

        return stock_items

    def get_asset_items(self):
        asset_items = []
        item_codes = list(set(item.item_code for item in self.get("items")))
        if item_codes:
            asset_items = frappe.db.get_values(
                "Item",
                {"name": ["in", item_codes], "is_fixed_asset": 1},
                pluck="name",
                cache=True,
            )

        return asset_items

    @frappe.whitelist()
    def get_items_from_purchase_invoice(self, purchase_invoices: list[str]):
        if not purchase_invoices:
            frappe.msgprint(_("No Purchase Invoices selected"))
            return

        frappe.has_permission("Bill Of Entry", "write", throw=True)
        frappe.has_permission("Purchase Invoice", "read", throw=True)

        existing_items = [
            item.pi_detail for item in self.get("items") if item.pi_detail
        ]
        item_to_add = get_pi_items(purchase_invoices)

        if not existing_items:
            self.items = []

        for item in item_to_add:
            if item.pi_detail not in existing_items:
                self.append("items", {**item})

        set_missing_values(self)

    def validate_qty(self):
        pi_item_names = [item.pi_detail for item in self.items]

        pi_qty_map = frappe._dict(
            frappe.get_all(
                "Purchase Invoice Item",
                filters={"name": ["in", pi_item_names]},
                fields=["name", "pending_boe_qty"],
                as_list=True,
            )
        )

        for item in self.items:
            if item.qty > pi_qty_map.get(item.pi_detail):
                frappe.throw(
                    _("Quantity of {0} is more than it's pending qty").format(
                        item.item_code
                    )
                )

    def update_pending_boe_qty(self):
        pi_item_names = [item.pi_detail for item in self.items]

        pi_item = frappe.qb.DocType("Purchase Invoice Item")
        boe_item = frappe.qb.DocType("Bill of Entry Item")

        submitted_boe_qty = (
            frappe.qb.from_(boe_item)
            .select(boe_item.pi_detail, Sum(boe_item.qty).as_("qty"))
            .where(boe_item.pi_detail.isin(pi_item_names))
            .where(boe_item.docstatus == 1)
            .groupby(boe_item.pi_detail)
        )

        (
            frappe.qb.update(pi_item)
            .left_join(submitted_boe_qty)
            .on(pi_item.name == submitted_boe_qty.pi_detail)
            .set(
                pi_item.pending_boe_qty,
                pi_item.qty - IfNull(submitted_boe_qty.qty, 0),
            )
            .where(pi_item.name.isin(pi_item_names))
            .run()
        )


def set_missing_values(source, target=None):
    if not target:
        target = source

    target.set_defaults()

    # Add default tax
    input_igst_account = get_gst_accounts_by_type(source.company, "Input").igst_account
    if not input_igst_account:
        return

    rate = (
        frappe.db.get_value(
            "Purchase Taxes and Charges",
            {
                "parenttype": "Purchase Taxes and Charges Template",
                "account_head": input_igst_account,
            },
            "rate",
        )
        or 0
    )

    has_igst_tax = any(
        tax.charge_type == "On Net Total"
        and tax.account_head == input_igst_account
        and tax.rate == rate
        and tax.gst_tax_type == "igst"
        for tax in source.taxes
    )

    if not has_igst_tax:
        valid_tax_row = {
            tax_row.account_head for tax_row in target.taxes if tax_row.account_head
        }
        if not valid_tax_row:
            target.taxes = []

        target.append(
            "taxes",
            {
                "charge_type": "On Net Total",
                "account_head": input_igst_account,
                "rate": rate,
                "gst_tax_type": "igst",
            },
        )

    target.set_taxes_and_totals()


@frappe.whitelist()
def make_bill_of_entry(source_name: str, target_doc: str | None = None):
    """
    Permission checked in get_mapped_doc
    """

    def update_item_qty(source, target, source_parent):
        target.qty = source.get("pending_boe_qty")
        if not target.project:
            target.project = source_parent.project

    doc = get_mapped_doc(
        "Purchase Invoice",
        source_name,
        {
            "Purchase Invoice": {
                "doctype": "Bill of Entry",
                "field_no_map": ["posting_date"],
                "validation": {
                    "docstatus": ["=", 1],
                    "gst_category": ["=", "Overseas"],
                },
            },
            "Purchase Invoice Item": {
                "doctype": "Bill of Entry Item",
                "field_map": {
                    "name": "pi_detail",
                    "taxable_value": "assessable_value",
                },
                "condition": lambda doc: doc.pending_boe_qty > 0,
                "postprocess": update_item_qty,
            },
        },
        target_doc,
        postprocess=set_missing_values,
    )

    return doc


@frappe.whitelist()
def make_journal_entry_for_payment(source_name: str, target_doc: str | None = None):
    """
    Permission checked in get_mapped_doc
    """

    def set_missing_values(source, target):
        target.voucher_type = "Bank Entry"
        target.posting_date = target.cheque_date = today()
        target.user_remark = "Payment against Bill of Entry {0}".format(source.name)

        company = frappe.get_cached_doc("Company", source.company)
        target.append(
            "accounts",
            {
                "account": source.customs_payable_account,
                "debit_in_account_currency": source.total_amount_payable,
                "reference_type": "Bill of Entry",
                "reference_name": source.name,
                "cost_center": company.cost_center,
            },
        )

        target.append(
            "accounts",
            {
                "account": company.default_bank_account or company.default_cash_account,
                "credit_in_account_currency": source.total_amount_payable,
                "cost_center": company.cost_center,
            },
        )

    doc = get_mapped_doc(
        "Bill of Entry",
        source_name,
        {
            "Bill of Entry": {
                "doctype": "Journal Entry",
                "validation": {
                    "docstatus": ["=", 1],
                },
            },
        },
        target_doc,
        postprocess=set_missing_values,
    )

    return doc


@frappe.whitelist()
def make_landed_cost_voucher(source_name: str, target_doc: str | None = None):
    """
    Permission checked in get_mapped_doc
    """

    def set_missing_values(source, target):
        items = get_items_for_landed_cost_voucher(source)
        if not items:
            frappe.throw(_("No items found for Landed Cost Voucher"))

        target.posting_date = today()
        target.distribute_charges_based_on = "Distribute Manually"

        # add references
        reference_docs = {item.parent: item.parenttype for item in items.values()}
        for parent, parenttype in reference_docs.items():
            target.append(
                "purchase_receipts",
                {
                    "receipt_document_type": parenttype,
                    "receipt_document": parent,
                },
            )

        # add items
        target.get_items_from_purchase_receipts()

        # update applicable charges
        total_customs_duty = 0
        for item in target.items:
            item.applicable_charges = items[item.purchase_receipt_item].customs_duty
            total_customs_duty += item.applicable_charges
            item.boe_detail = items[item.purchase_receipt_item].boe_detail

        # add taxes
        target.append(
            "taxes",
            {
                "expense_account": source.customs_expense_account,
                "description": "Customs Duty",
                "amount": total_customs_duty,
            },
        )

        if total_customs_duty != source.total_customs_duty:
            frappe.msgprint(
                _(
                    "Could not find purchase receipts for all items. Please check"
                    " manually."
                )
            )

        update_landed_cost_voucher_for_gst_expense(source, target)

    doc = get_mapped_doc(
        "Bill of Entry",
        source_name,
        {
            "Bill of Entry": {
                "doctype": "Landed Cost Voucher",
            },
        },
        target_doc,
        postprocess=set_missing_values,
    )

    return doc


def get_items_for_landed_cost_voucher(boe):
    """
    For creating landed cost voucher, it needs to be linked with transaction where stock was updated.
    This function will return items based on following conditions:
        1. Where stock was updated in Purchase Invoice
        2. Where stock was updated in Purchase Receipt
            a. Purchase Invoice was created from Purchase Receipt
            b. Purchase Receipt was created from Purchase Invoice

    Also, it will apportion customs duty for PI items.

    NOTE: Assuming business has consistent practice of creating PR and PI
    """
    invoice_details_map = get_purchase_invoice_details(boe)

    item_customs_map = {item.pi_detail: item.customs_duty for item in boe.items}
    item_name_map = {item.pi_detail: item.name for item in boe.items}

    # No PR
    all_items = []
    for pi in invoice_details_map:
        if pi.update_stock:
            for pi_item in pi._items:
                pi_item.customs_duty = item_customs_map.get(pi_item.name)
                pi_item.boe_detail = item_name_map.get(pi_item.name)

            all_items.extend(pi._items)

        # Creating PI from PR
        elif pi._items[0].purchase_receipt:
            pr_pi_map = {pi_item.pr_detail: pi_item.name for pi_item in pi._items}
            pr_items = frappe.get_all(
                "Purchase Receipt Item",
                fields="*",
                filters={"name": ["in", pr_pi_map.keys()], "docstatus": 1},
            )

            for pr_item in pr_items:
                pr_item.customs_duty = item_customs_map.get(pr_pi_map.get(pr_item.name))
                pr_item.boe_detail = item_name_map.get(pr_pi_map.get(pr_item.name))

            all_items.extend(pr_items)

        else:
            # Creating PR from PI (Qty split possible in PR)
            pr_items = frappe.get_all(
                "Purchase Receipt Item",
                fields="*",
                filters={"purchase_invoice": pi.name, "docstatus": 1},
            )

            item_qty_map = {item.name: item.qty for item in pi._items}

            for pr_item in pr_items:
                customs_duty_for_item = item_customs_map.get(
                    pr_item.purchase_invoice_item
                )
                total_qty = item_qty_map.get(pr_item.purchase_invoice_item)
                pr_item.customs_duty = customs_duty_for_item * pr_item.qty / total_qty
                pr_item.boe_detail = item_name_map.get(pr_item.purchase_invoice_item)

            all_items.extend(pr_items)

    return frappe._dict({item.name: item for item in all_items if item})


def get_purchase_invoice_details(boe):
    pi_names, pi_item_names = set(), set()
    for item in boe.items:
        pi_names.add(item.purchase_invoice)
        pi_item_names.add(item.pi_detail)

    # update_stock
    invoice_map = frappe._dict(
        frappe.get_all(
            "Purchase Invoice",
            filters={"name": ["in", pi_names]},
            fields=["name", "update_stock"],
            as_list=True,
        )
    )

    # items
    pi_items = frappe.get_all(
        "Purchase Invoice Item", filters={"name": ["in", pi_item_names]}, fields=["*"]
    )

    # build doc
    pi_details = {}
    for item in pi_items:
        name = item.parent
        invoice = pi_details.setdefault(
            name, frappe._dict(name=name, update_stock=invoice_map.get(name), _items=[])
        )
        invoice._items.append(item)

    return list(pi_details.values())


def get_pi_items(purchase_invoices):
    pi_item = frappe.qb.DocType("Purchase Invoice Item")
    pi = frappe.qb.DocType("Purchase Invoice")

    return (
        frappe.qb.from_(pi_item)
        .join(pi)
        .on(pi_item.parent == pi.name)
        .select(
            pi_item.item_code,
            pi_item.item_name,
            pi_item.parent.as_("purchase_invoice"),
            pi_item.pending_boe_qty.as_("qty"),
            pi_item.uom,
            pi_item.cost_center,
            pi_item.item_tax_template,
            pi_item.gst_treatment,
            pi_item.taxable_value.as_("assessable_value"),
            pi_item.taxable_value,
            IfNull(pi_item.project, pi.project).as_("project"),
            pi_item.name.as_("pi_detail"),
        )
        .where(pi_item.parent.isin(purchase_invoices))
        .where(pi_item.pending_boe_qty > 0)
        .run(as_dict=True)
    )


@frappe.whitelist()
def fetch_pending_boe_invoices(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: str | dict | frappe._dict,
):
    """
    Permission check not required as using get_list
    """
    filters = frappe._dict(filters)

    if txt and not filters.get("name"):
        filters.name = ["like", f"%{txt}%"]

    # TODO: fix required in frappe
    if filters.name and filters.name[1] is None:
        filters.name = ["!=", ""]

    return frappe.get_list(
        "Purchase Invoice",
        filters={
            **filters,
            "docstatus": 1,
            "gst_category": "Overseas",
            "pending_boe_qty": [">", 0],
        },
        fields=["name", "company", "company_gstin"],
        limit_start=start,
        limit_page_length=page_len,
        distinct=True,
    )
