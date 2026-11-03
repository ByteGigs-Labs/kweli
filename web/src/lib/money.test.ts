import { formatMoney } from "./money";

test("formats minor units with the currency's decimals", () => {
  const plain = (text: string) => text.replace(/\s/g, " ");
  expect(plain(formatMoney(80000, "USD"))).toBe("USD 800.00");
  expect(plain(formatMoney(150000, "EUR"))).toBe("EUR 1,500.00");
  expect(plain(formatMoney(1500, "JPY"))).toBe("JPY 1,500");
});
