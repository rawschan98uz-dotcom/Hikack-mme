/**
 * "Копилка" preview (same rule as backend finance/wallet.py): money reaching the monthly price
 * closes a month, the rest waits in the student's копилка.
 */
export interface WalletPreview {
  months: number;
  left: number;
  missing: number;
}

export function walletPreview(
  price: number | null | undefined,
  wallet: number | null | undefined,
  amount: number | null | undefined,
  discount = 0,
): WalletPreview | null {
  if (!price || price <= 0) return null;
  const total = (wallet || 0) + Math.max(0, amount || 0) + Math.max(0, discount || 0);
  const months = Math.floor(total / price);
  const left = total - months * price;
  return { months, left, missing: left > 0 ? price - left : 0 };
}

export function formatSum(value: number): string {
  return Math.round(value).toLocaleString('ru-RU');
}
