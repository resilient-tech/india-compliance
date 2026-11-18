from playwright.sync_api import Locator, Page, expect

from ui_tests.pages.base_page import DESK_TIMEOUT


def wait_for_input_value(locator: Locator, value: str, timeout: int = DESK_TIMEOUT) -> None:
    expect(locator).to_have_value(value, timeout=timeout)


def wait_for_network_idle(page: Page, timeout: int = DESK_TIMEOUT) -> None:
    page.wait_for_load_state("networkidle", timeout=timeout)


def dismiss_modals(form, timeout: int = DESK_TIMEOUT) -> list[str]:
    modals = form.get_modals()
    closed: list[str] = []

    while count := modals.count():
        modal = modals.last
        closed.append((modal.locator(".modal-title").first.inner_text() or "").strip())
        modal.locator(".btn-modal-close").first.click()
        expect(modals).to_have_count(count - 1, timeout=timeout)

    return closed
