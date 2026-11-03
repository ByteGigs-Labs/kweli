import pytest

pytest.importorskip("langchain_core")

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

from agent.spike import ALLOWED_METHODS, run  # noqa: E402


class ToolCallingFake(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@tool
def create_invoice(invoice_number: str, amount: str) -> str:
    """Create a draft invoice."""
    return '{"id": "INV2-SPIKE", "status": "DRAFT"}'


def test_spike_can_only_draft_and_read_invoices():
    assert set(ALLOWED_METHODS) == {"generate_invoice_number", "create_invoice", "get_invoice"}


def test_loop_runs_tools_and_returns_final_answer():
    replies = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_invoice",
                        "args": {"invoice_number": "7", "amount": "10"},
                        "id": "c1",
                    }
                ],
            ),
            AIMessage(content="Draft INV2-SPIKE created for $10.00."),
        ]
    )
    calls: list[str] = []
    answer = run("Invoice x", ToolCallingFake(messages=replies), [create_invoice], calls.append)
    assert answer == "Draft INV2-SPIKE created for $10.00."
    assert calls[0].startswith("tool call: create_invoice")


def test_unknown_tools_are_refused():
    replies = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "send_invoice", "args": {"invoice_id": "X"}, "id": "c1"}],
            ),
            AIMessage(content="I can't send invoices."),
        ]
    )
    calls: list[str] = []
    answer = run("Send it", ToolCallingFake(messages=replies), [create_invoice], calls.append)
    assert calls == []
    assert answer == "I can't send invoices."
