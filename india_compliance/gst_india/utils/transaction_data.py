import re

import frappe
from frappe import _
from frappe.utils import format_date, get_link_to_form, getdate, rounded

from india_compliance.gst_india.constants import (
    E_INVOICE_MASTER_CODES_URL,
    GST_TAX_RATES,
    GST_TAX_TYPES,
)
from india_compliance.gst_india.constants.e_waybill import (
    TRANSPORT_MODES,
    VEHICLE_TYPES,
)
from india_compliance.gst_india.utils import (
    get_gst_accounts_by_type,
    get_gst_uom,
    get_validated_country_code,
    validate_invoice_number,
    validate_pincode,
)

REGEX_MAP = {
    1: re.compile(r"[^A-Za-z0-9]"),
    2: re.compile(r"[^A-Za-z0-9\-\/. ]"),
    3: re.compile(r"[^A-Za-z0-9@#\-\/,&.(*) ]"),
}


class GSTTransactionData:
    DATE_FORMAT = "dd/mm/yyyy"

    def __init__(self, doc):
        self.doc = doc
        self.settings = frappe.get_cached_doc("GST Settings")
        self.sandbox_mode = self.settings.sandbox_mode
        self.transaction_details = frappe._dict()

        gst_type = "Output"
        self.party_name_field = "customer_name"

        if self.doc.doctype == "Purchase Invoice":
            self.party_name_field = "supplier_name"
            if self.doc.is_reverse_charge != 1:
                # for with reverse charge, gst_type is Output
                # this will ensure zero taxes in transaction details
                gst_type = "Input"

        self.party_name = self.doc.get(self.party_name_field)

        # "CGST Account - TC": "cgst_account"
        self.gst_accounts = {
            v: k
            for k, v in get_gst_accounts_by_type(self.doc.company, gst_type).items()
        }

    def set_transaction_details(self):
        rounding_adjustment = self.rounded(self.doc.base_rounding_adjustment)
        if self.doc.is_return:
            rounding_adjustment = -rounding_adjustment

        grand_total_fieldname = (
            "base_grand_total"
            if self.doc.disable_rounded_total
            else "base_rounded_total"
        )

        total = 0
        total_taxable_value = 0

        for row in self.doc.items:
            total += row.taxable_value

            if row.gst_treatment in ("Taxable", "Zero-Rated"):
                total_taxable_value += row.taxable_value

        self.transaction_details.update(
            {
                "company_name": self.sanitize_value(self.doc.company),
                "party_name": self.sanitize_value(
                    self.party_name
                    or frappe.db.get_value(
                        self.doc.doctype, self.party_name, self.party_name_field
                    )
                ),
                "date": format_date(self.doc.posting_date, self.DATE_FORMAT),
                "total": abs(self.rounded(total)),
                "total_taxable_value": abs(self.rounded(total_taxable_value)),
                "total_non_taxable_value": abs(
                    self.rounded(total - total_taxable_value)
                ),
                "rounding_adjustment": rounding_adjustment,
                "grand_total": abs(self.rounded(self.doc.get(grand_total_fieldname))),
                "grand_total_in_foreign_currency": (
                    abs(self.rounded(self.doc.grand_total))
                    if self.doc.currency != "INR"
                    else ""
                ),
                "discount_amount": (
                    abs(self.rounded(self.doc.base_discount_amount))
                    if self.doc.get("is_cash_or_non_trade_discount")
                    else 0
                ),
                "company_gstin": self.doc.company_gstin,
                "name": self.doc.name,
                "other_charges": 0,
            }
        )
        self.update_transaction_details()
        self.update_transaction_tax_details()

    def update_transaction_details(self):
        # to be overrridden
        pass

    def update_transaction_tax_details(self):
        tax_total_keys = tuple(f"total_{tax}_amount" for tax in GST_TAX_TYPES)

        for key in tax_total_keys:
            self.transaction_details[key] = 0

        for row in self.doc.taxes:
            if not row.tax_amount or row.account_head not in self.gst_accounts:
                continue

            tax = self.gst_accounts[row.account_head][:-8]
            self.transaction_details[f"total_{tax}_amount"] = abs(
                self.rounded(row.base_tax_amount_after_discount_amount)
            )

        # Other Charges
        current_total = 0
        for key in ("total", "rounding_adjustment", *tax_total_keys):
            current_total += self.transaction_details.get(key)

        current_total -= self.transaction_details.discount_amount
        other_charges = self.transaction_details.grand_total - current_total

        if 0 > other_charges > -0.1:
            # other charges cannot be negative
            # handle cases where user has higher precision than 2
            self.transaction_details.rounding_adjustment = self.rounded(
                self.transaction_details.rounding_adjustment + other_charges
            )
        else:
            self.transaction_details.other_charges = self.rounded(other_charges)

    def validate_mode_of_transport(self, throw=True):
        def _throw(error):
            if throw:
                frappe.throw(error, title=_("Invalid Transporter Details"))

        if not (mode_of_transport := self.doc.mode_of_transport):
            return _throw(
                _(
                    "Either GST Transporter ID or Mode of Transport is required to"
                    " generate e-Waybill"
                )
            )

        if mode_of_transport == "Road" and not self.doc.vehicle_no:
            return _throw(
                _(
                    "Vehicle Number is required to generate e-Waybill for supply via"
                    " Road"
                )
            )
        if mode_of_transport == "Ship" and not (self.doc.vehicle_no and self.doc.lr_no):
            return _throw(
                _(
                    "Vehicle Number and L/R No is required to generate e-Waybill for"
                    " supply via Ship"
                )
            )
        if mode_of_transport in ("Rail", "Air") and not self.doc.lr_no:
            return _throw(
                _(
                    "L/R No. is required to generate e-Waybill for supply via Rail"
                    " or Air"
                )
            )

        return True

    def set_transporter_details(self):
        self.transaction_details.distance = (
            self.doc.distance if self.doc.distance and self.doc.distance < 4000 else 0
        )

        if self.validate_mode_of_transport(False):
            self.transaction_details.update(
                {
                    "mode_of_transport": TRANSPORT_MODES.get(
                        self.doc.mode_of_transport
                    ),
                    "vehicle_type": VEHICLE_TYPES.get(self.doc.gst_vehicle_type) or "R",
                    "vehicle_no": self.sanitize_value(self.doc.vehicle_no, regex=1),
                    "lr_no": self.sanitize_value(
                        self.doc.lr_no, regex=2, max_length=15
                    ),
                    "lr_date": (
                        format_date(self.doc.lr_date, self.DATE_FORMAT)
                        if self.doc.lr_no
                        else ""
                    ),
                    "gst_transporter_id": self.doc.gst_transporter_id or "",
                    "transporter_name": (
                        self.sanitize_value(
                            self.doc.transporter_name, regex=3, max_length=25
                        )
                        if self.doc.transporter_name
                        else ""
                    ),
                }
            )

        #  Part A Only
        elif self.doc.gst_transporter_id:
            for_json = getattr(self, "for_json", False)
            self.transaction_details.update(
                {
                    "mode_of_transport": 1 if for_json else "",
                    "vehicle_type": "R" if for_json else "",
                    "vehicle_no": "",
                    "lr_no": "",
                    "lr_date": "",
                    "gst_transporter_id": self.doc.gst_transporter_id,
                    "transporter_name": self.doc.transporter_name or "",
                }
            )

    def validate_transaction(self):
        if self.doc.docstatus > 1:
            frappe.throw(
                msg=_(
                    "Cannot generate e-Waybill or e-Invoice for a cancelled transaction"
                ),
                title=_("Invalid Document State"),
            )

        validate_invoice_number(self.doc)
        posting_date = getdate(self.doc.posting_date)

        if posting_date > getdate():
            frappe.throw(
                msg=_("Posting Date cannot be greater than Today's Date"),
                title=_("Invalid Data"),
            )

        # compare posting date and lr date, only if lr no is set
        if (
            self.doc.lr_no
            and self.doc.lr_date
            and posting_date > getdate(self.doc.lr_date)
        ):
            frappe.throw(
                msg=_("Posting Date cannot be greater than LR Date"),
                title=_("Invalid Data"),
            )

    def validate_non_gst_items(self):
        validate_non_gst_items(self.doc)

    def get_all_item_details(self):
        all_item_details = []

        # progressive error of item tax amounts
        self.rounding_errors = {f"{tax}_rounding_error": 0 for tax in GST_TAX_TYPES}

        items = self.doc.items
        if self.doc.group_same_items:
            items = self.group_same_items()

        for row in items:
            item_details = frappe._dict(
                {
                    "item_no": row.idx,
                    "qty": abs(self.rounded(row.qty, 3)),
                    "taxable_value": abs(self.rounded(row.taxable_value)),
                    "hsn_code": row.gst_hsn_code,
                    "item_name": self.sanitize_value(
                        row.item_name, regex=3, max_length=300
                    ),
                    "uom": get_gst_uom(row.uom, self.settings),
                    "gst_treatment": row.gst_treatment,
                }
            )
            self.update_item_details(item_details, row)
            self.update_item_tax_details(item_details, row)
            all_item_details.append(item_details)

        return all_item_details

    def group_same_items(self):
        validate_unique_hsn_and_uom(self.doc)
        grouped_items = {}
        idx = 1

        for row in self.doc.items:
            item = grouped_items.setdefault(
                row.item_code,
                frappe._dict(
                    {**row.as_dict(), "idx": 0, "qty": 0.00, "taxable_value": 0.00}
                ),
            )

            if not item.idx:
                item.idx = idx
                idx += 1

            item.qty += row.qty
            item.taxable_value += row.taxable_value

        return list(grouped_items.values())

    def set_item_list(self):
        self.item_list = []

        for item_details in self.get_all_item_details():
            self.item_list.append(self.get_item_data(item_details))

    def update_item_details(self, item_details, item):
        # to be overridden
        pass

    def update_item_tax_details(self, item_details, item):
        for tax in GST_TAX_TYPES:
            item_details.update({f"{tax}_amount": 0, f"{tax}_rate": 0})

        for row in self.doc.taxes:
            if not row.tax_amount or row.account_head not in self.gst_accounts:
                continue

            # Remove '_account' from 'cgst_account'
            tax = self.gst_accounts[row.account_head][:-8]
            tax_rate = self.rounded(
                frappe.parse_json(row.item_wise_tax_detail).get(
                    item.item_code or item.item_name
                )[0],
                3,
            )

            # considers senarios where same item is there multiple times
            tax_amount = self.get_progressive_item_tax_amount(
                (
                    tax_rate * item.qty
                    if row.charge_type == "On Item Quantity"
                    else tax_rate * item.taxable_value / 100
                ),
                tax,
            )

            item_details.update(
                {
                    f"{tax}_rate": tax_rate,
                    f"{tax}_amount": tax_amount,
                }
            )

        tax_rate = sum(
            self.rounded(item_details.get(f"{tax}_rate", 0), 3)
            for tax in GST_TAX_TYPES[:3]
        )

        validate_gst_tax_rate(tax_rate, item)

        item_details.update(
            {
                "tax_rate": tax_rate,
                "total_value": abs(
                    self.rounded(
                        item_details.taxable_value
                        + sum(
                            self.rounded(item_details.get(f"{tax}_amount", 0))
                            for tax in GST_TAX_TYPES
                        )
                    ),
                ),
            }
        )

    def get_progressive_item_tax_amount(self, amount, tax_type):
        """
        Helper function to calculate progressive tax amount for an item to remove
        rounding errors.
        """
        error_field = f"{tax_type}_rounding_error"
        error_amount = self.rounding_errors[error_field]

        response = self.rounded(amount + error_amount)
        self.rounding_errors[error_field] = amount + error_amount - response

        return abs(response)

    def get_address_details(self, address_name, validate_gstin=False):
        address = frappe.get_cached_value(
            "Address",
            address_name,
            (
                "name",
                "address_title",
                "address_line1",
                "address_line2",
                "city",
                "pincode",
                "country",
                "gstin",
                "gst_state_number",
            ),
            as_dict=True,
        )

        if address.gst_state_number == "97":  # For Other Territory
            address.pincode = "999999"

        if address.country != "India":
            address.gst_state_number = "96"
            address.pincode = "999999"

        self.check_missing_address_fields(address, validate_gstin)

        error_context = {
            "reference_doctype": "Address",
            "reference_name": address.name,
        }

        return frappe._dict(
            {
                "gstin": address.get("gstin") or "URP",
                "state_number": address.gst_state_number,
                "address_title": self.sanitize_value(
                    address.address_title,
                    regex=2,
                    fieldname="address_title",
                    **error_context,
                ),
                "address_line1": self.sanitize_value(
                    address.address_line1,
                    regex=3,
                    min_length=1,
                    fieldname="address_line1",
                    **error_context,
                ),
                "address_line2": self.sanitize_value(address.address_line2, regex=3),
                "city": self.sanitize_value(
                    address.city,
                    regex=3,
                    max_length=50,
                    fieldname="city",
                    **error_context,
                ),
                "pincode": int(address.pincode),
                "country_code": get_validated_country_code(address.country),
            }
        )

    def check_missing_address_fields(self, address, validate_gstin=False):
        fieldnames = [
            "address_title",
            "address_line1",
            "city",
            "pincode",
            "gst_state_number",
        ]

        if validate_gstin:
            fieldnames.append("gstin")

        for fieldname in fieldnames:
            if address.get(fieldname):
                continue

            frappe.throw(
                _(
                    "{0} is missing in Address {1}. Please update it and try again."
                ).format(
                    frappe.bold(frappe.get_meta("Address").get_label(fieldname)),
                    frappe.bold(address.name),
                ),
                title=_("Missing Address Details"),
            )

        validate_pincode(address)

    def get_item_data(self, item_details):
        pass

    @staticmethod
    def sanitize_data(d):
        """Adapted from https://stackoverflow.com/a/27974027/4767738"""

        def _is_truthy(v):
            return v or v == 0

        if isinstance(d, dict):
            return {
                k: v
                for k, v in (
                    (k, GSTTransactionData.sanitize_data(v)) for k, v in d.items()
                )
                if _is_truthy(v)
            }

        if isinstance(d, list):
            return [
                v for v in map(GSTTransactionData.sanitize_data, d) if _is_truthy(v)
            ]

        return d

    @staticmethod
    def rounded(value, precision=2):
        return rounded(value, precision)

    @staticmethod
    def sanitize_value(
        value: str,
        regex=None,
        min_length=3,
        max_length=100,
        truncate=True,
        *,
        fieldname=None,
        reference_doctype=None,
        reference_name=None,
    ):
        """
        Sanitize value to make it suitable for GST JSON sent for e-Waybill and e-Invoice.

        If fieldname, reference doctype and reference name are present,
        error will be thrown for invalid values instead of sanitizing them.

        Parameters:
        ----------
        @param value: Value to be sanitized
        @param regex: Regex Key (from REGEX_MAP) to substitute unacceptable characters
        @param min_length (default: 3): Minimum length of the value that is acceptable
        @param max_length (default: 100): Maximum length of the value that is acceptable
        @param truncate (default: True): Truncate the value if it exceeds max_length
        @param fieldname: Fieldname for which the value is being sanitized
        @param reference_doctype: DocType of the document that contains the field
        @param reference_name: Name of the document that contains the field

        Returns:
        ----------
        @return: Sanitized value

        """

        def _throw(message, **format_args):
            if not (fieldname and reference_doctype and reference_name):
                return

            message = message.format(
                field=_(frappe.get_meta(reference_doctype).get_label(fieldname)),
                **format_args,
            )

            frappe.throw(
                _("{reference_doctype} {reference_link}: {message}").format(
                    reference_doctype=_(reference_doctype),
                    reference_link=frappe.bold(
                        get_link_to_form(reference_doctype, reference_name)
                    ),
                    message=message,
                ),
                title=_("Invalid Data for GST Upload"),
            )

        if not value or len(value) < min_length:
            return _throw(
                _("{field} must be at least {min_length} characters long"),
                min_length=min_length,
            )

        original_value = value

        if regex:
            value = re.sub(REGEX_MAP[regex], "", value)

        if len(value) < min_length:
            if not original_value.isascii():
                return _throw(_("{field} must only consist of ASCII characters"))

            return _throw(
                _("{field} consists of invalid characters: {invalid_chars}"),
                invalid_chars=frappe.bold(
                    "".join(set(original_value).difference(value))
                ),
            )

        if not truncate and len(value) > max_length:
            return

        return value[:max_length]


def validate_non_gst_items(doc, throw=True):
    if doc.items[0].gst_treatment == "Non-GST":
        if not throw:
            return

        frappe.throw(
            _("This action cannot be performed for transactions with non-GST items"),
            title=_("Invalid Data"),
        )

    return True


def validate_unique_hsn_and_uom(doc):
    """
    Raise an exception if
    - Group same items is checked and
    - Same item code has different HSN code or UOM
    """

    if not doc.group_same_items:
        return

    def _throw(label, value):
        frappe.throw(
            _(
                "Row #{0}: {1}: {2} is different for Item: {3}. Grouping of items is"
                " not possible."
            ).format(item.idx, label, value, frappe.bold(item.item_code))
        )

    def _validate_unique(item_wise_values, field_value, label):
        values_set = item_wise_values.setdefault(item.item_code, set())
        values_set.add(field_value)

        if len(values_set) > 1:
            _throw(label, field_value)

    item_wise_uom = {}
    item_wise_hsn = {}

    for item in doc.items:
        _validate_unique(item_wise_uom, item.get("uom"), _("UOM"))
        _validate_unique(item_wise_hsn, item.get("gst_hsn_code"), _("HSN Code"))


def validate_gst_tax_rate(tax_rate, item):
    if tax_rate not in GST_TAX_RATES:
        frappe.throw(
            _(
                "Row #{0}: GST tax rate {1} for Item {2} is not permitted for"
                " generating e-Invoice as it doesn't adhere to the e-Invoice"
                " Masters.<br><br> Check valid tax rates <a href='{3}'>here</a>."
            ).format(
                item.idx,
                frappe.bold(f"{tax_rate}%"),
                item.item_code,
                E_INVOICE_MASTER_CODES_URL,
            ),
            title=_("Invalid Tax Rate"),
        )
