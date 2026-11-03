const ZERO_DECIMAL = new Set(["HUF", "JPY", "TWD"]);

export function formatMoney(amountMinor: number, currency: string, locale = "en-KE") {
  const digits = ZERO_DECIMAL.has(currency) ? 0 : 2;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    currencyDisplay: "code",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(amountMinor / 10 ** digits);
}
