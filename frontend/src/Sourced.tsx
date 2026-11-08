// Rendering a figure together with where it came from.
//
// Protocol section 21.6 mark 1 is enforced in the backend, where an unsourced figure cannot be
// constructed. This component is the half that matters to a reader: the source is on the figure in
// the interface too, as a title a hover reveals and as text the evidence drawer prints in full.
// A number on a screen with no way to ask where it came from is the thing this project exists to
// avoid producing.

import type { Money, Sourced as SourcedFigure } from "./types";

// Formatting, which is presentation and not computation: the unrounded value stays in the payload.
export function formatValue(value: number | boolean | null, unit: string | null): string {
  if (value === null) return "not reported";
  if (typeof value === "boolean") return value ? "pass" : "FAIL";
  // A whole number renders whole. The first version chose digits by magnitude alone, so a count of
  // 14 episodes rendered as "14.0" and 4 abstentions as "4.00", which reads as a measurement with
  // spurious precision rather than a count of things. JSON does not carry the distinction between
  // an int and a float, so the value itself is what decides.
  if (Number.isInteger(value)) {
    const whole = value.toLocaleString("en-GB");
    return unit ? `${whole} ${unit}` : whole;
  }
  const magnitude = Math.abs(value);
  const digits = magnitude >= 1000 ? 0 : magnitude >= 10 ? 1 : magnitude >= 1 ? 2 : 4;
  const text = value.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return unit ? `${text} ${unit}` : text;
}

export function Figure({ figure }: { figure: SourcedFigure }): JSX.Element {
  const hint = [
    `source: ${figure.source}`,
    figure.denominator ? `denominator: ${figure.denominator}` : null,
  ]
    .filter(Boolean)
    .join("\n");
  return (
    <span className="sourced mono" title={hint}>
      {formatValue(figure.value, figure.unit)}
    </span>
  );
}

// A money tile renders its reason when there is no amount, which is the honest state and not a
// degraded one. Section 20.3: an illustration that circulates as a finding is the failure mode, so
// the amount and its assumption cannot be separated even in the markup.
export function MoneyFigure({ money }: { money: Money }): JSX.Element {
  if (money.amount === null || money.amount.value === null) {
    return <div className="value none">{money.reason ?? "not computed"}</div>;
  }
  return (
    <>
      <div className="value">
        <Figure figure={money.amount} />
      </div>
      <div className="denominator">{money.assumption}</div>
    </>
  );
}
