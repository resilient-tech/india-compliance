from ..setup import add_company_fixtures


def make_company_fixtures(doc, method=None):
    if doc.country != "India":
        return

    add_company_fixtures(doc.name)
