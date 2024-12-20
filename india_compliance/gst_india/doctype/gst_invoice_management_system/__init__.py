import frappe
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Abs, IfNull, Sum

from india_compliance.gst_india.api_classes.taxpayer_returns import IMSAPI
from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    update_previous_ims_action as _update_previous_ims_action,
)
from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import (
    enqueue_link_integration_request,
    enqueue_notification,
    status_code_map,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    GSTIN_RULES,
    PAN_RULES,
    BaseUtil,
    Reconciler,
)
from india_compliance.gst_india.utils.gstr_2 import ims


class IMSReconciler(Reconciler):
    ORIGINAL_VS_AMENDED = (
        {
            "original": "B2B",
            "amended": "B2BA",
            "doc_type": "Invoice",
        },
        {
            "original": "CDNR",
            "amended": "CDNRA",
            "doc_type": "Credit Note",
        },
        {
            "original": "CDNR",
            "amended": "CDNRA",
            "doc_type": "Debit Note",
        },
    )

    def auto_reconcile_invoices(self, filters):
        """
        Reconcile purchases and inward supplies.
        """
        for row in self.ORIGINAL_VS_AMENDED:
            filters.update(row)
            self.category = row["original"]

            purchases = PurchaseInvoice().get_unmatched_purchase_invoices(filters)
            inward_supplies = InwardSupply().get_unmatched_inward_supplies(filters)

            # GSTIN Level matching
            self.reconcile_for_rules(GSTIN_RULES, purchases, inward_supplies)

            # PAN Level matching
            purchases = self.get_pan_level_data(purchases)
            inward_supplies = self.get_pan_level_data(inward_supplies)
            self.reconcile_for_rules(PAN_RULES, purchases, inward_supplies)


class InwardSupply:
    def __init__(self, **kwargs):
        self.inward_supply = frappe.qb.DocType("GST Inward Supply")

    def get_all_inward_supplies(self, names=None, filters=None):
        if not filters:
            filters = frappe._dict()

        query = self.get_base_inward_supply_query(["action", "doc_type"])

        if names:
            query = query.where(self.inward_supply.name.isin(names))

        query = get_query_with_filters(self.inward_supply, query, filters)

        return query.run(as_dict=True)

    def get_unmatched_inward_supplies(self, filters):
        categories = [filters.original, filters.amended]

        query = self.get_base_inward_supply_query()
        query = get_query_with_filters(self.inward_supply, query, filters)

        data = (
            query.where(IfNull(self.inward_supply.match_status, "") == "")
            .where(self.inward_supply.classification.isin(categories))
            .where(self.inward_supply.doc_type == filters.doc_type)
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_base_inward_supply_query(self, additional_fields=None):
        fields = self.get_fields(additional_fields=additional_fields)

        return (
            frappe.qb.from_(self.inward_supply)
            .select(
                *fields,
                ConstantColumn("GST Inward Supply").as_("doctype"),
                Case()
                .when(
                    (
                        self.inward_supply.ims_action
                        == self.inward_supply.previous_ims_action
                    ),
                    False,
                )
                .else_(True)
                .as_("pending_upload"),
            )
            .where(IfNull(self.inward_supply.previous_ims_action, "") != "")
        )

    def get_fields(self, additional_fields=None):
        fields = [
            "supplier_gstin",
            "supplier_name",
            "company_gstin",
            "bill_no",
            "bill_date",
            "name",
            "is_reverse_charge",
            "place_of_supply",
            "link_name",
            "link_doctype",
            "match_status",
            "ims_action",
            "previous_ims_action",
            "supply_type",
            "classification",
            "is_pending_action_allowed",
            "supplier_return_form",
        ]

        if additional_fields:
            fields += additional_fields

        fields = [self.inward_supply[field] for field in fields]
        fields += self.get_tax_fields()

        return fields

    def get_tax_fields(self):
        fields = GST_TAX_TYPES[:-1] + ("taxable_value",)
        return [self.inward_supply[field] for field in fields]


class PurchaseInvoice:
    def __init__(self):
        self.purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        self.purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")

    def get_all_purchases(self, names=None, filters=None):
        if not filters:
            filters = frappe._dict()

        query = self.get_base_purchase_query()

        if names:
            query = query.where(self.purchase_invoice.name.isin(names))

        query = get_query_with_filters(self.purchase_invoice, query, filters)

        purchases = query.run(as_dict=True)

        return {doc.name: doc for doc in purchases}

    def get_unmatched_purchase_invoices(self, filters):
        gst_category = (
            "Registered Regular",
            "Tax Deductor",
            "Input Service Distributor",
        )
        is_return = (
            1
            if filters.category in ["CDNR", "CDNRA"]
            and filters.doc_type == "Credit Note"
            else 0
        )

        query = self.get_base_purchase_query()
        query = get_query_with_filters(self.purchase_invoice, query, filters)

        data = (
            query.where(self.purchase_invoice.gst_category.isin(gst_category))
            .where(self.purchase_invoice.reconciliation_status == "Unreconciled")
            .where(self.purchase_invoice.is_return == is_return)
            .where(self.purchase_invoice.is_reverse_charge == 0)
            .where(
                self.purchase_invoice.ineligibility_reason
                != "ITC restricted due to PoS rules"
            )
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_base_purchase_query(self):
        fields = self.get_fields()

        return (
            frappe.qb.from_(self.purchase_invoice)
            .left_join(self.purchase_invoice_item)
            .on(self.purchase_invoice_item.parent == self.purchase_invoice.name)
            .select(
                Abs(Sum(self.purchase_invoice_item.taxable_value)).as_("taxable_value"),
                *fields,
                ConstantColumn("Purchase Invoice").as_("doctype"),
            )
            .groupby(self.purchase_invoice.name)
        )

    def get_fields(self, additional_fields=None):
        fields = [
            "supplier_gstin",
            "supplier_name",
            "bill_no",
            "bill_date",
            "name",
            "company",
            "company_gstin",
            "is_reverse_charge",
            "place_of_supply",
        ]

        if additional_fields:
            fields += additional_fields

        fields = [self.purchase_invoice[field] for field in fields]
        fields += self.get_tax_fields()

        return fields

    def get_tax_fields(self):
        return [
            query_tax_amount(self.purchase_invoice_item, f"{tax_type}_amount").as_(
                tax_type
            )
            for tax_type in GST_TAX_TYPES
        ]


def get_query_with_filters(doc, query, filters):
    if filters.get("company"):
        query = query.where(doc.company == filters.company)

    if filters.get("company_gstin"):
        query = query.where(doc.company_gstin == filters.company_gstin)

    return query


def query_tax_amount(doc, field):
    return Abs(Sum(getattr(doc, field)))


def get_invoices_to_upload(company_gstin):
    _InwardSupply = InwardSupply()
    query = _InwardSupply.get_base_inward_supply_query(
        additional_fields=[
            "doc_type",
            "is_amended",
            "sup_return_period",
            "document_value",
        ]
    )
    gst_inward_supply_list = query.where(
        _InwardSupply.inward_supply.ims_action
        != _InwardSupply.inward_supply.previous_ims_action
    ).run(as_dict=True)

    upload_data, reset_data = convert_data_to_gov_format(
        gst_inward_supply_list, company_gstin
    )

    return upload_data, reset_data


def convert_data_to_gov_format(gst_inward_supply_list, company_gstin):
    category_key_map = {
        "Invoice_0": "b2b",
        "Invoice_1": "b2ba",
        "Debit Note_0": "b2bdn",
        "Debit Note_1": "b2bdna",
        "Credit Note_0": "b2bcn",
        "Credit Note_1": "b2bcna",
    }

    upload_data = {}
    reset_data = {}
    key_invoice_map = {}

    for invoice in gst_inward_supply_list:
        key = f"{invoice.doc_type}_{invoice.is_amended}"
        if key_invoice_map.get(key):
            key_invoice_map[key].append(invoice)
        else:
            key_invoice_map[key] = [invoice]

    for key, invoices in key_invoice_map.items():
        category = category_key_map[key]
        _class = getattr(ims, category.upper())(company_gstin)
        upload_invoices = []
        reset_invoices = []

        for invoice in invoices:
            data = {
                **_class.update_transaction_to_gov_format(invoice),
                **_class.get_category_details(invoice),
            }

            if invoice.ims_action != "No Action":
                upload_invoices.append(data)
            else:
                reset_invoices.append(data)

        if upload_invoices:
            upload_data[category] = upload_invoices

        if reset_invoices:
            reset_data[category] = reset_invoices

    return upload_data, reset_data


def update_return_log(doc, token, action, request_id, status=None):
    if not token:
        return

    row = {
        "request_type": action,
        "token": token,
        "creation_time": frappe.utils.now_datetime(),
    }

    if status:
        row["status"] = status

    doc.append("actions", row)
    doc.save()
    enqueue_link_integration_request(token, request_id)


def process_upload_or_reset_ims(return_log, action):
    response = {"status_cd": "P"}  # dummy_response
    if not return_log.actions:
        return response

    api = IMSAPI(return_log.gstin)

    doc = return_log.get_unprocessed_action(action)
    if not doc:
        return response

    response = api.get_request_status(doc.token)
    status_cd = response.get("status_cd")

    erroneous_invoices = []
    if status_cd != "IP":
        doc.db_set({"status": status_code_map.get(status_cd)})
        enqueue_notification(
            return_log.return_period,
            doc.request_type,
            status_cd,
            return_log.gstin,
            api.request_id if status_cd == "ER" else None,
        )

    if status_cd == "PE":
        erroneous_invoices = get_erroneous_invoices(response.get("error_report"))

    if status_cd in ["P", "PE"]:
        # Exclude erroneous invoices from previous IMS action update
        # This is enqueued because linking of integration request is enqueued
        frappe.enqueue(
            update_previous_ims_action,
            queue="long",
            return_log=doc,
            erroneous_invoices=erroneous_invoices,
        )

    return response


def get_erroneous_invoices(report):
    invoice_names = []
    for error_list in report.values():
        for error in error_list:
            for invoice in error.get("inv"):
                invoice_names.append(f"{invoice.get('inum')}_{error.get('stin')}")

    return invoice_names


def get_uploaded_invoices(integration_request):
    request_data = frappe.parse_json(
        frappe.db.get_value(
            "Integration Request", {"name": integration_request}, "data"
        )
    )

    return request_data["body"]["data"]["invdata"]


def update_previous_ims_action(return_log, erroneous_invoices):
    integration_request = return_log.integration_request
    uploded_invoices = get_uploaded_invoices(integration_request)

    invoices_to_update = []
    for category, invoices in uploded_invoices.items():
        _class = getattr(ims, category.upper())()
        invoices_to_update.extend(_class.get_all_transactions(invoices))

    for invoice in invoices_to_update:
        if f"{invoice.bill_no}_{invoice.supplier_gstin}" in erroneous_invoices:
            continue

        _update_previous_ims_action(invoice)
