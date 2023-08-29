import json

import frappe

from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.custom_fields import delete_custom_fields

user = None


def execute():
    global user
    user = frappe.session.user

    migrate_e_waybill_fields()
    migrate_e_invoice_fields()
    migrate_e_invoice_request_log()
    delete_e_invoice_fields()


def migrate_e_waybill_fields():
    if not frappe.db.has_column("Sales Invoice", "eway_bill_validity"):
        return

    docs = frappe.get_all(
        "Sales Invoice",
        filters={"eway_bill_validity": ("not in", ("", None))},
        fields=(
            "name",
            "eway_bill_validity",
            "ewaybill",
            "eway_bill_cancelled",
            "creation",
            "ack_date",
        ),
    )

    fields = (
        "name",
        "creation",
        "modified",
        "owner",
        "modified_by",
        "reference_name",
        "e_waybill_number",
        "valid_upto",
        "is_cancelled",
    )
    values = []
    for doc in docs:
        values.append(
            [
                doc.ewaybill,
                doc.ack_date or doc.creation,
                doc.ack_date or doc.creation,
                user,
                user,
                doc.name,
                doc.ewaybill,
                parse_datetime(doc.eway_bill_validity),
                doc.eway_bill_cancelled,
            ]
        )

    frappe.db.bulk_insert(
        "e-Waybill Log", fields=fields, values=values, ignore_duplicates=True
    )


def migrate_e_invoice_fields():
    if not frappe.db.has_column("Sales Invoice", "irn_cancelled"):
        return

    docs = frappe.get_all(
        "Sales Invoice",
        filters={"irn": ("not in", ("", None))},
        fields=(
            "name",
            "irn_cancelled",
            "ack_no",
            "ack_date",
            "irn_cancel_date",
            "signed_einvoice",
            "signed_qr_code",
            "irn",
        ),
    )

    values = []
    fields = (
        "name",
        "creation",
        "modified",
        "owner",
        "modified_by",
        "irn",
        "sales_invoice",
        "is_cancelled",
        "acknowledgement_number",
        "acknowledged_on",
        "cancelled_on",
        "invoice_data",
        "signed_qr_code",
    )
    for doc in docs:
        if doc.signed_einvoice and not doc.ack_no:
            try:
                signed_einvoice = json.loads(doc.signed_einvoice)
                doc.ack_no = signed_einvoice.get("AckNo")
                doc.ack_date = signed_einvoice.get("AckDt")

            except json.decoder.JSONDecodeError:
                pass

        values.append(
            [
                doc.irn,
                doc.ack_date,
                doc.ack_date,
                user,
                user,
                doc.irn,
                doc.name,
                doc.irn_cancelled,
                doc.ack_no,
                doc.ack_date,
                doc.irn_cancel_date,
                doc.signed_einvoice,
                doc.signed_qr_code,
            ]
        )

    frappe.db.bulk_insert(
        "e-Invoice Log", fields=fields, values=values, ignore_duplicates=True
    )


def migrate_e_invoice_request_log():
    if not frappe.db.table_exists("E Invoice Request Log"):
        return

    if frappe.db.exists(
        "Integration Request",
        {"integration_request_service": "Migrated from e-Invoice Request Log"},
    ):
        return

    # Using db.get_values instead of get_all to avoid retrieving meta,
    # since the DocType E Invoice Request Log gets deleted in ERPNext patch
    docs = frappe.db.get_values(
        "E Invoice Request Log",
        filters={},
        fieldname=(
            "user",
            "creation",
            "url",
            "reference_invoice",
            "headers",
            "data",
            "response",
            "modified",
            "modified_by",
            "name",
            "owner",
        ),
        as_dict=True,
    )

    values = []
    fields = (
        "name",
        "creation",
        "modified",
        "owner",
        "modified_by",
        "integration_request_service",
        "status",
        "url",
        "request_headers",
        "data",
        "output",
        "reference_doctype",
        "reference_docname",
    )
    for doc in docs:
        values.append(
            [
                doc.name,
                doc.creation,
                doc.modified,
                doc.user or doc.owner,
                doc.modified_by,
                "Migrated from e-Invoice Request Log",
                "Completed",
                doc.url,
                doc.headers,
                doc.data,
                doc.response,
                "Sales Invoice",
                doc.reference_invoice,
            ]
        )

    frappe.db.bulk_insert(
        "Integration Request", fields=fields, values=values, ignore_duplicates=True
    )


def delete_e_invoice_fields():
    FIELDS_TO_DELETE = {
        "Sales Invoice": [
            {
                "fieldname": "failure_description",
                "label": "e-Invoice Failure Description",
                "fieldtype": "Code",
                "options": "JSON",
                "hidden": 1,
                "insert_after": "einvoice_status",
                "no_copy": 1,
                "print_hide": 1,
                "read_only": 1,
            },
            {
                "fieldname": "irn_cancelled",
                "label": "IRN Cancelled",
                "fieldtype": "Check",
                "no_copy": 1,
                "print_hide": 1,
                "depends_on": "eval: doc.irn",
                "allow_on_submit": 1,
                "insert_after": "customer",
            },
            {
                "fieldname": "eway_bill_validity",
                "label": "e-Waybill Validity",
                "fieldtype": "Data",
                "no_copy": 1,
                "print_hide": 1,
                "depends_on": "ewaybill",
                "read_only": 1,
                "allow_on_submit": 1,
                "insert_after": "ewaybill",
                "translatable": 0,
            },
            {
                "fieldname": "eway_bill_cancelled",
                "label": "e-Waybill Cancelled",
                "fieldtype": "Check",
                "no_copy": 1,
                "print_hide": 1,
                "depends_on": "eval:(doc.eway_bill_cancelled === 1)",
                "read_only": 1,
                "allow_on_submit": 1,
                "insert_after": "customer",
            },
            {
                "fieldname": "einvoice_section",
                "label": "e-Invoice Fields",
                "fieldtype": "Section Break",
                "insert_after": "gst_vehicle_type",
                "print_hide": 1,
                "hidden": 1,
            },
            {
                "fieldname": "ack_no",
                "label": "Ack. No.",
                "fieldtype": "Data",
                "read_only": 1,
                "hidden": 1,
                "insert_after": "einvoice_section",
                "no_copy": 1,
                "print_hide": 1,
                "translatable": 0,
            },
            {
                "fieldname": "ack_date",
                "label": "Ack. Date",
                "fieldtype": "Data",
                "read_only": 1,
                "hidden": 1,
                "insert_after": "ack_no",
                "no_copy": 1,
                "print_hide": 1,
                "translatable": 0,
            },
            {
                "fieldname": "irn_cancel_date",
                "label": "Cancel Date",
                "fieldtype": "Data",
                "read_only": 1,
                "hidden": 1,
                "insert_after": "ack_date",
                "no_copy": 1,
                "print_hide": 1,
                "translatable": 0,
            },
            {
                "fieldname": "signed_einvoice",
                "label": "Signed e-Invoice",
                "fieldtype": "Code",
                "options": "JSON",
                "hidden": 1,
                "insert_after": "irn_cancel_date",
                "no_copy": 1,
                "print_hide": 1,
                "read_only": 1,
            },
            {
                "fieldname": "signed_qr_code",
                "label": "Signed QRCode",
                "fieldtype": "Code",
                "options": "JSON",
                "hidden": 1,
                "insert_after": "signed_einvoice",
                "no_copy": 1,
                "print_hide": 1,
                "read_only": 1,
            },
            {
                "fieldname": "qrcode_image",
                "label": "QRCode",
                "fieldtype": "Attach Image",
                "hidden": 1,
                "insert_after": "signed_qr_code",
                "no_copy": 1,
                "print_hide": 1,
                "read_only": 1,
            },
        ]
    }
    delete_custom_fields(FIELDS_TO_DELETE)
