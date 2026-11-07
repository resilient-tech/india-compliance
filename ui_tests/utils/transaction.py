from ui_tests.utils import wait_for_input_value, wait_for_network_idle


def verify_field_value(form, fieldname, expected):
    wait_for_input_value(form.control(form.page, fieldname, "input"), str(expected))


def verify_autofilled_values(form, values):
    form.page.wait_for_timeout(100)
    wait_for_network_idle(form.page)

    doc = form.doc()

    for fieldname, expected in values.items():
        assert doc.get(fieldname) == expected, (
            f"{fieldname}: expected {expected!r}, got {doc.get(fieldname)!r}"
        )


def verify_taxes_table(form, rows, tablefield="taxes"):
    form.wait_for_row_count(tablefield, len(rows))
    actual_rows = form.doc().get(tablefield) or []

    for actual, expected in zip(actual_rows, rows, strict=True):
        for fieldname, value in expected.items():
            got = actual.get(fieldname)
            matched = str(value) in str(got or "") if isinstance(value, str) else got == value

            assert matched, f"{tablefield}.{fieldname}: expected {value!r}, got {got!r}"


def fill_items_table(form, rows, tablefield="items"):
    form.fill_table(tablefield, rows)
