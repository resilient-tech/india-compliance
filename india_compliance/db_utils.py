import itertools

import frappe
from frappe.query_builder import Case

# Temporary utility functions to update multiple documents in bulk.
# Reference Frappe PR: https://github.com/frappe/frappe/pull/28483


def bulk_update(
    doctype: str, docs: list[dict], chunk_size: int = 100, commit: bool = False
):
    """
    :param doctype: DocType to update
    :param docs: Dictionary of key (docname) and values to update
    :param chunk_size: Number of documents to update in a single transaction
    :param commit: Commit after each chunk

    docs should be in the following format:
    ```py
    {
        "docname1": {
            "field1": "value1",
            "field2": "value2",
            ...
        },
        "docname2": {
            "field1": "value1",
            "field2": "value2",
            ...
        },
    }
    ```

    Note:
        - The fields to update should be the same for all documents.
        - Bigger chunk sizes could be less performant. Use appropriate chunk size based on the number of fields to update.

    """
    if not docs:
        return

    iterator = iter(docs)
    total_docs = len(docs)

    for __ in range(0, total_docs, chunk_size):
        docs_map = {k: docs[k] for k in itertools.islice(iterator, chunk_size)}

        build_query_and_update_in_bulk(doctype, docs_map)

        if commit:
            frappe.db.commit()  # nosemgrep


def build_query_and_update_in_bulk(doctype: str, docs: dict):
    """
    :param doctype: DocType to update
    :param docs: Dictionary of key (docname) and values to update (must < 100)

    ---

    docs should be in the following format:
    ```py
    {
        "docname1": {
            "field1": "value1",
            "field2": "value2",
            ...
        },
        "docname2": {
            "field1": "value1",
            "field2": "value2",
            ...
        },
    }
    ```

    ---

    Query will be built as:
    ```sql
    UPDATE `tabItem`
    SET `status` = CASE
        WHEN `name` = 'Item-1' THEN 'Close'
        WHEN `name` = 'Item-2' THEN 'Open'
        WHEN `name` = 'Item-3' THEN 'Close'
        WHEN `name` = 'Item-4' THEN 'Cancelled'
    end,
    `description` = CASE
        WHEN `name` = 'Item-1' THEN 'This is the first task'
        WHEN `name` = 'Item-2' THEN 'This is the second task'
        WHEN `name` = 'Item-3' THEN 'This is the third task'
        WHEN `name` = 'Item-4' THEN 'This is the fourth task'
    end
    WHERE  `name` IN ( 'Item-1', 'Item-2', 'Item-3', 'Item-4' )
    ```
    """
    if not docs:
        return

    dt = frappe.qb.DocType(doctype)
    update_query = frappe.qb.update(dt)

    fields_to_update = next(iter(docs.values())).keys()
    docnames = list(docs.keys())

    # Initialize CASE
    conditions = frappe._dict({field: Case() for field in fields_to_update})

    # WHEN conditions
    for docname, row in docs.items():
        for field, value in row.items():
            conditions[field].when(dt.name == docname, value)

    # update query
    for field in conditions:
        update_query = update_query.set(dt[field], conditions[field])

    update_query.where(dt.name.isin(docnames)).run()
