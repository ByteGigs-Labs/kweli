"""Spike: Claude + PayPal Agent Toolkit create one SANDBOX draft invoice from a sentence.

The agent may only create drafts. Sending stays a human action (the approval gate).

Usage:
  pip install -r requirements-agent.txt
  python -m agent.spike "Invoice ap@acme.test 10 USD for a logo design, due in 7 days"
"""

import json
import sys
from datetime import date

from api.config import get_settings

ALLOWED_METHODS = ("generate_invoice_number", "create_invoice", "get_invoice")
MAX_STEPS = 6

SYSTEM_PROMPT = """You are Kweli's invoicing assistant for a freelancer.
Today is {today}. Create a DRAFT PayPal invoice from the user's request.
Rules:
- Get the next invoice number first, then create the invoice with it.
- Use only the email, amount, currency, description and due date the user gave.
  If any of them is missing, stop and ask instead of guessing.
- Never send the invoice. The freelancer sends it themselves after reviewing it.
- Finish with the draft invoice ID and a one-line summary."""


def build_tools():
    from agent.paypal_tools import paypal_tools

    return paypal_tools(ALLOWED_METHODS)


def build_model():
    from langchain_anthropic import ChatAnthropic

    settings = get_settings()
    if settings.anthropic_api_key is None:
        raise SystemExit("Set ANTHROPIC_API_KEY.")
    return ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key.get_secret_value(),
        temperature=0,
        max_tokens=1024,
    )


def run(request: str, model, tools, log=print) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    by_name = {tool.name: tool for tool in tools}
    llm = model.bind_tools(tools)
    messages = [
        SystemMessage(SYSTEM_PROMPT.format(today=date.today().isoformat())),
        HumanMessage(request),
    ]
    for _ in range(MAX_STEPS):
        reply = llm.invoke(messages)
        messages.append(reply)
        if not reply.tool_calls:
            return reply.content if isinstance(reply.content, str) else json.dumps(reply.content)
        for call in reply.tool_calls:
            tool = by_name.get(call["name"])
            if tool is None:
                result = f"Tool {call['name']} is not allowed."
            else:
                log(f"tool call: {call['name']} {json.dumps(call['args'])[:500]}")
                result = tool.invoke(call["args"])
            messages.append(ToolMessage(content=str(result)[:4000], tool_call_id=call["id"]))
    return "Stopped: too many steps without a final answer."


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 1
    if get_settings().paypal_env != "sandbox":
        print("Refusing to run against live. Set PAYPAL_ENV=sandbox.")
        return 1
    print(run(" ".join(argv), build_model(), build_tools()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
