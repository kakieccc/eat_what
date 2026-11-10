import { useId, useState } from "react";
import { Slider } from "radix-ui";
import { integerBudget, type Budget } from "../lib/schemas";

export function BudgetRange({ value, onChange, disabled = false, invalid = false }: {
  value: Budget;
  onChange: (value: Budget) => void;
  disabled?: boolean;
  invalid?: boolean;
}) {
  const id = useId();
  const lower = Math.min(10000, Math.max(0, Number.parseInt(value.min || "0", 10) || 0));
  const upper = Math.min(10000, Math.max(lower, Number.parseInt(value.max || "500", 10) || 0));
  const [ceiling, setCeiling] = useState(() => Math.max(500, Math.ceil(upper / 100) * 100));
  const sliderMax = Math.max(ceiling, Math.ceil(upper / 100) * 100);
  return (
    <div className="budget-range">
      <div className="budget-inputs">
        <label className="budget-field" htmlFor={`${id}-min`}>
          <input id={`${id}-min`} aria-label="最低预算" inputMode="decimal"
            value={value.min ?? "0"} disabled={disabled} aria-invalid={invalid}
            onChange={(event) => onChange({ ...value, min: event.target.value })}
            onBlur={() => onChange({ ...value, min: integerBudget(value.min || "0") })} />
        </label>
        <span aria-hidden="true">—</span>
        <label className="budget-field" htmlFor={`${id}-max`}>
          <input id={`${id}-max`} aria-label="最高预算" inputMode="decimal" placeholder="不限"
            value={value.max ?? ""} disabled={disabled} aria-invalid={invalid}
            onChange={(event) => onChange({ ...value, max: event.target.value })}
            onBlur={() => onChange({ ...value, max: value.max ? integerBudget(value.max) : null })} />
        </label>
      </div>
      <Slider.Root className="budget-slider" min={0} max={sliderMax} step={1}
        value={[lower, upper]} disabled={disabled}
        onValueChange={([min, max]) => {
          setCeiling(sliderMax);
          onChange({ min: String(min), max: String(max) });
        }}>
        <Slider.Track className="budget-slider-track"><Slider.Range className="budget-slider-selection" /></Slider.Track>
        <Slider.Thumb className="budget-slider-thumb" aria-label="预算下限" />
        <Slider.Thumb className="budget-slider-thumb" aria-label="预算上限" />
      </Slider.Root>
      <div className="budget-slider-scale" aria-hidden="true"><span>¥0</span><span>¥{sliderMax}</span></div>
    </div>
  );
}
