import { formatMoney } from "./money";

test("formats minor units with the currency's decimals", () => {
  expect(formatMoney(80000, "USD", "en-US")).toBe("$800.00");
  expect(formatMoney(1500, "JPY", "en-US")).toBe("¥1,500");
});
