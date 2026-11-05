"""PayPal Customer Disputes v1: read a dispute, submit evidence, and the sandbox-only controls.

Spec: paypal-rest-api-specifications/openapi/customer_disputes_v1.json
- provide-evidence is multipart/form-data: an `input` part (application/json) with
  {"evidences": [...]}, plus one part per file. Only allowed while the dispute is
  WAITING_FOR_SELLER_RESPONSE and the dispute's HATEOAS links include `provide_evidence`.
- require-evidence and adjudicate only exist in the sandbox, for disputes UNDER_REVIEW.
"""

import json
from dataclasses import dataclass

from paypal.client import PayPalClient

BASE = "/v1/customer/disputes"
SANDBOX_ONLY = frozenset({"require_evidence", "adjudicate"})


@dataclass(frozen=True)
class EvidenceFile:
    name: str
    data: bytes
    mime: str


def links(dispute: dict) -> set[str]:
    """The actions PayPal allows right now, from the dispute's HATEOAS links."""
    found = set()
    for link in dispute.get("links") or []:
        rel = str(link.get("rel") or "").replace("-", "_").lower()
        if rel and rel != "self":
            found.add(rel)
    return found


class Disputes:
    def __init__(self, client: PayPalClient) -> None:
        self.client = client

    def get(self, dispute_id: str) -> dict:
        return self.client.get(f"{BASE}/{dispute_id}")

    def provide_evidence(
        self,
        dispute_id: str,
        evidences: list[dict],
        files: list[EvidenceFile],
        request_id: str,
    ) -> dict:
        parts: list = [("input", (None, json.dumps({"evidences": evidences}), "application/json"))]
        parts += [
            (f"file{index}", (item.name, item.data, item.mime))
            for index, item in enumerate(files, start=1)
        ]
        return self.client.request(
            "POST", f"{BASE}/{dispute_id}/provide-evidence", files=parts, request_id=request_id
        )

    def require_evidence(self, dispute_id: str, action: str = "SELLER_EVIDENCE") -> dict:
        self._sandbox_only()
        return self.client.post(f"{BASE}/{dispute_id}/require-evidence", json={"action": action})

    def adjudicate(self, dispute_id: str, outcome: str) -> dict:
        self._sandbox_only()
        if outcome not in ("SELLER_FAVOR", "BUYER_FAVOR"):
            raise ValueError("outcome must be SELLER_FAVOR or BUYER_FAVOR")
        return self.client.post(
            f"{BASE}/{dispute_id}/adjudicate", json={"adjudication_outcome": outcome}
        )

    def _sandbox_only(self) -> None:
        if self.client.settings.paypal_env != "sandbox":
            raise PermissionError("This PayPal call only exists in the sandbox")
