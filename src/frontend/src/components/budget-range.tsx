import { useId } from "react";
import { Slider } from "radix-ui";
import { integerBudget, type Budget } from "../lib/schemas";

export function BudgetRange({ value, onChange, disabled = false, invalid = false }: {
  value: Budget;
  onChange: (value: Budget) => void;
  disabled?: boolean;
  invalid?: boolean;
}) {
  const id = useId();
  // Reserve the last fifth of the track for an open upper bound.
  const openEnd = 625;
  const lower = Math.min(500, Math.max(1, Number.parseInt(value.min || "1", 10) || 1));
  const upper = value.max === null ? openEnd : Math.min(500, Math.max(lower, Number.parseInt(value.max || "500", 10) || 1));
  return (
    <div className="budget-range">
      <div className="budget-inputs">
        <label className="budget-field" htmlFor={`${id}-min`}>
          <input id={`${id}-min`} aria-label="最低预算" inputMode="decimal"
            value={value.min ?? "1"} disabled={disabled} aria-invalid={invalid}
            onChange={(event) => onChange({ ...value, min: event.target.value })}
            onBlur={() => {
              const minimum = integerBudget(value.min || "1");
              onChange({ ...value, min: minimum === "0" ? "1" : minimum });
            }} />
        </label>
        <span aria-hidden="true">—</span>
        <label className="budget-field" htmlFor={`${id}-max`}>
          <input id={`${id}-max`} aria-label="最高预算" inputMode="decimal" placeholder="不限"
            value={value.max ?? ""} disabled={disabled} aria-invalid={invalid}
            onChange={(event) => onChange({ ...value, max: event.target.value })}
            onBlur={() => onChange({ ...value, max: value.max ? integerBudget(value.max) : null })} />
        </label>
      </div>
      <Slider.Root className="budget-slider" min={1} max={openEnd} step={1}
        value={[lower, upper]} disabled={disabled}
        onValueChange={([min, max]) => {
          onChange({ min: String(Math.min(min, 500)), max: max > 500 ? null : String(max) });
        }}>
        <Slider.Track className="budget-slider-track"><Slider.Range className="budget-slider-selection" /></Slider.Track>
        <Slider.Thumb className="budget-slider-thumb" aria-label="预算下限" aria-valuemax={500} aria-valuetext={`${value.min || "1"} 元`} />
        <Slider.Thumb className="budget-slider-thumb" aria-label="预算上限"
          aria-valuetext={value.max === null ? "上限不限" : `${value.max} 元`}
          onKeyDown={(event) => {
            if (!disabled && value.max === null && ["ArrowLeft", "ArrowDown", "PageDown"].includes(event.key)) {
              event.preventDefault();
              onChange({ min: String(lower), max: "500" });
            }
          }} />
      </Slider.Root>
      <div className="budget-slider-scale" aria-hidden="true">
        <span>¥1</span><span className="budget-slider-limit">¥500</span><span>500+</span>
      </div>
    </div>
  );
}
