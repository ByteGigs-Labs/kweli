from datetime import date

from api.services.extract import check_against_thread

THREAD = """Hi Amina, it's Jordan from Acme Ltd (jordan@acmeltd.com).
We'd love a new logo: 3 concepts and final files in SVG and PNG.
Budget is $1,250 total. Can you deliver by 20 November 2026?
Amina: Yes, USD 1,250 works for me."""


def raw(**overrides) -> dict:
    return {
        "client_name": "Acme Ltd",
        "client_email": "jordan@acmeltd.com",
        "title": "Logo design",
        "scope": "New logo with three concepts",
        "deliverables": ["3 logo concepts", "Final SVG and PNG files", "  "],
        "amount": "1,250",
        "currency": "usd",
        "due_date": "2026-11-20",
    } | overrides


def test_clean_extraction_is_kept():
    draft = check_against_thread(raw(), THREAD)
    assert draft.client_email == "jordan@acmeltd.com"
    assert draft.amount == "1250"
    assert draft.currency == "USD"
    assert draft.due_date == date(2026, 11, 20)
    assert draft.deliverables == ["3 logo concepts", "Final SVG and PNG files"]
    assert draft.missing == []
    assert draft.notes == []


def test_invented_email_is_dropped():
    draft = check_against_thread(raw(client_email="payments@attacker.com"), THREAD)
    assert draft.client_email is None
    assert "client_email" in draft.missing
    assert "isn't in the thread" in draft.notes[0]


def test_invented_amount_is_dropped():
    draft = check_against_thread(raw(amount="12500"), THREAD)
    assert draft.amount is None
    assert "amount" in draft.missing


def test_unsupported_currency_is_dropped():
    draft = check_against_thread(raw(currency="KES"), THREAD)
    assert draft.currency is None
    assert "PayPal can't invoice in KES" in draft.notes[0]


def test_garbage_output_yields_an_empty_form():
    draft = check_against_thread({"due_date": "next week-ish", "deliverables": "x"}, THREAD)
    assert draft.client_name is None
    assert set(draft.missing) >= {"client_name", "amount", "due_date"}
    assert draft.notes


def test_missing_fields_are_listed():
    draft = check_against_thread(raw(due_date=None, client_name=None), THREAD)
    assert draft.missing == ["client_name", "due_date"]
