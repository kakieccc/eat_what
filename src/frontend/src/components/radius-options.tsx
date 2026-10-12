import { ToggleGroup } from "radix-ui";
import { radiusValues, type SearchRadius } from "../lib/schemas";
import { formatDistance } from "../lib/utils";

export function RadiusOptions({
  value,
  onChange,
  disabled = false,
  invalid = false,
}: {
  value: SearchRadius | undefined;
  onChange: (value: SearchRadius) => void;
  disabled?: boolean;
  invalid?: boolean;
}) {
  return (
    <ToggleGroup.Root
      type="single"
      className="four-options"
      value={value === undefined ? "" : String(value)}
      onValueChange={(next) => {
        const radius = radiusValues.find((item) => String(item) === next);
        if (radius !== undefined) onChange(radius);
      }}
      disabled={disabled}
      aria-label="搜索半径"
      aria-invalid={invalid || undefined}
    >
      {radiusValues.map((radius) => (
        <ToggleGroup.Item key={radius} value={String(radius)}>
          {formatDistance(radius)}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
