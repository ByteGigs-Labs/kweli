import { render, screen, within } from "@testing-library/react";
import { ProofChain } from "./ProofChain";

test("each link says whether its proof is on file", () => {
  render(
    <ProofChain
      links={[
        { name: "Invoice", detail: "INV-1", state: "proven" },
        { name: "Deliverable", detail: "Not uploaded", state: "missing" },
      ]}
    />,
  );
  const chain = screen.getByRole("list", { name: "Proof chain" });
  const items = within(chain).getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(within(chain).getByText("Invoice").parentElement).toHaveTextContent("on file");
  expect(within(chain).getByText("Deliverable").parentElement).toHaveTextContent("missing");
});
