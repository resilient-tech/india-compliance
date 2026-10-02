# UI Tests

Browser tests for the Desk, written with
[Playwright&#39;s Python bindings](https://playwright.dev/python/docs/intro)
and run by `pytest`. `bench run-tests` cannot run them — it is frappe's
unittest runner and finds no `TestCase`.

## Install

`bench setup requirements --dev` installs `pytest`, `pytest-playwright`,
`pytest-timeout` and `python-dotenv` from `pyproject.toml`. It does **not**
install a browser — pip ships the driver, not the binary. Download it once:

```bash
bench setup requirements --dev
playwright install chromium
```

## One-time setup

Run the tests against a dedicated test site, populated with test data:

```bash
bench --site <site_name> execute india_compliance.tests.before_tests
```

## Configure

Copy the example file, and set `SITE` and `SITE_PORT` to match the server you
just started. `conftest.py` loads `.env` directly:

```bash
cp .env.example .env
```

Edit the configuration in `.env` to match your setup.

## Run

With the server up:

```bash
cd <bench>/apps/india_compliance/ui_tests
source <bench>/env/bin/activate

# everything
pytest

# a single file
pytest tests/test_purchase_invoice.py

# a single test
pytest tests/test_purchase_invoice.py::TestPurchaseInvoice::test_in_state_supplier_gets_cgst_and_sgst
```

### Run with a visible browser (headed mode)

The browser is headless by default. Add `--headed` to watch the run in a
visible window:

```bash
# everything, in a visible browser
pytest --headed

# one file, slowed down enough to follow
pytest --headed --slowmo 1000 tests/test_purchase_invoice.py --timeout=0
```

`--slowmo` takes a delay in milliseconds, applied before every action. To
stop on a line and step through the rest in the Playwright Inspector, call
`page.pause()` inside the test.

### Traces, video and screenshots

`--tracing=retain-on-failure --video=retain-on-failure --screenshot=only-on-failure` are already set in `pyproject.toml`, so a failing test leaves its artifacts under `test-results/`.

```bash
playwright show-trace test-results/<test-name>/trace.zip
```

To keep the artifacts for passing tests too, override on the command line:

```bash
pytest --tracing=on --video=on --screenshot=on
```

## Writing a test

Wrappers around Playwright locators live in `pages/base_page.py` (`BasePage`,
the Desk) and `pages/form_page.py` (`FormPage`, one open form).

The `form_page` fixture is autouse, so `self.form_page("Purchase Invoice")`
gives you an open form on a logged-in desk.

```python
class TestPurchaseInvoice:
    @pytest.fixture(scope="class", autouse=True)
    @staticmethod
    def setup(request, site):
        request.cls.supplier = frappe.get_doc(
            "Supplier", "_Test Registered Supplier"
        )
        request.cls.item = frappe.get_doc("Item", "_Test Trading Goods 1")

    def test_something(self):
        form = self.form_page("Purchase Invoice")
        form.fill_fields(
            {"supplier": self.supplier.name, "bill_no": "UI-TEST-001"}
        )
        fill_items_table(
            form, [{"item_code": self.item.name, "qty": 1, "rate": 100}]
        )
        form.save()
```

Read records with `frappe.get_doc` in the class-scoped `setup` fixture.
**CI has only what `india_compliance.tests.before_tests` seeds from
`tests/test_records.json`** — a record you created by hand locally does not
exist there, and the test fails with `DoesNotExistError`.

Assert anything a client script computes **before** the save. Move it after,
and a server hook setting the same field will make a broken client script
look fine.

The `doc` fixture reads a document the browser committed and deletes it when
the test ends, cancelling it first if submitted. `form.save()` registers its
own saves; pass anything else through it yourself. Cleanup errors are ignored,
so a submitted invoice with linked GL Entries can survive — a known limitation.

```python
def test_something(self, doc):
    ...
    doc("Purchase Invoice", name)    # read it, and delete it at test end
```

## Recording with codegen

Codegen opens two windows — a browser, and an inspector that writes out the
test as you click. Record from the `ui_tests` directory:

```bash
cd <bench>/apps/india_compliance/ui_tests
```

**First time** — creates `.auth/admin.json`. Log in as
Administrator in the window that opens, then close it; the session is written
to that file:

```bash
playwright codegen --save-storage=.auth/admin.json \
  "http://<site_name>:8000/login?redirect-to=/app"
```

**Every time after** — load that session, and the recorder opens straight on
an authenticated desk:

```bash
playwright codegen --load-storage=.auth/admin.json \
  "http://<site_name>:8000/app"
```

What comes out is a draft, not a test — a flat script of raw locators.
Refactor it onto `BasePage` and `FormPage` before committing: the recorded
locators break on the next layout change, the page objects do not.
