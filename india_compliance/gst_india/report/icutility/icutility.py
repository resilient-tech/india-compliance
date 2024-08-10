# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt


from india_compliance.gst_india.constants import ORIGINAL_VS_AMENDED
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.__init__ import (
    ReconciledData,
    Reconciler,
)


def execute(filters=None):
    # reconcile purchases and inward supplies
    _Reconciler = Reconciler(**filters)
    for row in ORIGINAL_VS_AMENDED:
        _Reconciler.reconcile(row["original"], row["amended"])

    obj = ReconciledData(**filters)
    reconciliation_data = obj.get()

    return get_columns(reconciliation_data), reconciliation_data


def get_columns(data):
    columns = []
    if not data:
        return
    for key in data[0].keys():
        columns.append(
            {
                "fieldname": key,
                "fieldtype": "Data",
            }
        )
    return columns
