from api.logging_config import redact


def test_paypal_access_tokens_are_redacted():
    line = "calling PayPal with A21AAJ3k9xQxxxxxxxxxxxxxxxxxxxxxx"
    assert "A21AAJ3k9xQ" not in redact(line)


def test_bearer_headers_are_redacted():
    assert "abc.def" not in redact("Authorization: Bearer abc.def")


def test_secret_assignments_are_redacted():
    assert "hunter2" not in redact("client_secret=hunter2")


def test_access_token_fields_are_redacted():
    assert "eyJsecret" not in redact('{"access_token": "eyJsecret"}')


def test_plain_messages_are_untouched():
    assert redact("invoice INV-0042 paid") == "invoice INV-0042 paid"
