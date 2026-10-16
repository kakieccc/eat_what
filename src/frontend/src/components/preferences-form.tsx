import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { SlidersHorizontal } from "lucide-react";
import {
  preferencesSchema,
  cuisines,
  isSearchRadius,
  type Preferences,
  type PreferencesSnapshot,
} from "../lib/schemas";
import { formatDistance } from "../lib/utils";
import { RadiusOptions } from "./radius-options";
import { Button } from "./ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetTrigger,
} from "./ui/sheet";
export function PreferencesForm({
  initial,
  onSubmit,
  label,
  busy = false,
  personal = false,
}: {
  initial: PreferencesSnapshot;
  onSubmit: (value: Preferences) => void | Promise<void>;
  label: string;
  busy?: boolean;
  personal?: boolean;
}) {
  const [advanced, setAdvanced] = useState(false);
  const {
    register,
    setError,
    clearErrors,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<Preferences, unknown, Preferences>({
    resolver: zodResolver(preferencesSchema),
    defaultValues: {
      ...initial,
      radiusMeters: isSearchRadius(initial.radiusMeters)
        ? initial.radiusMeters
        : undefined,
    },
  });
  const radius = watch("radiusMeters"),
    chosen = watch("preferredFoods"),
    excluded = watch("excludedFoods");
  const toggle = (field: "preferredFoods" | "excludedFoods", item: string) => {
    const current = watch(field);
    setValue(
      field,
      current.includes(item)
        ? current.filter((c) => c !== item)
        : [...current, item],
      { shouldValidate: true },
    );
  };
  return (
    <form
      onChange={() => clearErrors("root")}
      onSubmit={handleSubmit(async (value) => {
        clearErrors();
        try {
          await onSubmit({
            ...value,
            budgetPerPerson: {
              min:
                value.budgetPerPerson.min === ""
                  ? null
                  : value.budgetPerPerson.min,
              max:
                value.budgetPerPerson.max === ""
                  ? null
                  : value.budgetPerPerson.max,
            },
          });
        } catch (error) {
          setError("root", {
            message: error instanceof Error ? error.message : "提交失败",
          });
        }
      })}
      className="preference-form"
    >
      <fieldset>
        <legend>
          人均预算 <span>元 / 人</span>
        </legend>
        <div className="budget-inputs">
          <label className="sr-only" htmlFor="budget-min">
            最低预算
          </label>
          <input
            id="budget-min"
            inputMode="decimal"
            placeholder="不限"
            {...register("budgetPerPerson.min")}
          />
          <span>—</span>
          <label className="sr-only" htmlFor="budget-max">
            最高预算
          </label>
          <input
            id="budget-max"
            inputMode="decimal"
            placeholder="不限"
            {...register("budgetPerPerson.max")}
          />
        </div>
        {(errors.budgetPerPerson?.min ||
          errors.budgetPerPerson?.max ||
          errors.budgetPerPerson?.message) && (
          <p className="error" role="alert">
            {errors.budgetPerPerson?.min?.message ||
              errors.budgetPerPerson?.max?.message ||
              errors.budgetPerPerson?.message}
          </p>
        )}
      </fieldset>
      <fieldset data-invalid={!!errors.radiusMeters || undefined}>
        <legend>搜索半径</legend>
        <RadiusOptions
          value={radius}
          onChange={(value) =>
            setValue("radiusMeters", value, {
              shouldValidate: true,
              shouldDirty: true,
            })
          }
          disabled={busy || isSubmitting}
          invalid={!!errors.radiusMeters}
        />
        {errors.radiusMeters && (
          <p className="error" role="alert">
            {errors.radiusMeters.message}
          </p>
        )}
        <p className="muted">以确认位置为中心的直线范围。</p>
        {!isSearchRadius(initial.radiusMeters) && !isSearchRadius(radius) && (
          <p className="warning-text">
            旧记录的半径为 {formatDistance(initial.radiusMeters)}
            ，请重新选择搜索范围。
          </p>
        )}
      </fieldset>
      <fieldset>
        <legend>今天想吃什么</legend>
        <div className="chips">
          <button
            type="button"
            aria-pressed={!chosen.length}
            onClick={() => setValue("preferredFoods", [])}
          >
            不限
          </button>
          {cuisines.slice(0, 6).map((c) => (
            <button
              type="button"
              key={c}
              aria-pressed={chosen.includes(c)}
              onClick={() => toggle("preferredFoods", c)}
            >
              {c}
            </button>
          ))}
        </div>
      </fieldset>
      {!personal && (
        <label className="field-label">
          补充说明 <span>可选</span>
          <textarea
            placeholder="想吃热乎的，今天不太想吃面…"
            rows={3}
            {...register("requestText")}
          />
          {errors.requestText && (
            <span className="error" role="alert">
              {errors.requestText.message}
            </span>
          )}
        </label>
      )}
      <Sheet open={advanced} onOpenChange={setAdvanced}>
        <SheetTrigger asChild>
          <Button type="button" variant="ghost" className="advanced">
            <SlidersHorizontal size={16} />
            {personal
              ? "更多偏好 · 口味与不想吃的"
              : "更多条件 · 人数、场景与不想吃的"}
          </Button>
        </SheetTrigger>
        <SheetContent side="bottom" className="advanced-sheet">
          <SheetHeader>
            <SheetTitle>把这一餐，说得更具体</SheetTitle>
            <SheetDescription>
              {personal
                ? "保存常用条件，用于下次推荐。"
                : "条件只用于本次推荐，未知数据会明确提示。"}
            </SheetDescription>
          </SheetHeader>
          <div className="sheet-fields">
            {(
              [
                ["preferredFoods", "偏好的食物"],
                ["allowedFoods", "只考虑这些食物（任选其一）"],
                ["excludedFoods", "排除的食物"],
                ["softPreferences", "口味与场景"],
              ] as const
            ).map(([field, label]) => (
              <label className="field-label" key={field}>
                {label}
                <input
                  aria-label={label}
                  name={field}
                  defaultValue={watch(field).join("，")}
                  key={watch(field).join("，")}
                  placeholder="用逗号分隔，可填写菜系或菜品"
                  onBlur={(e) => {
                    setValue(
                      field,
                      e.target.value
                        .split(/[,，]/)
                        .map((v) => v.trim())
                        .filter(Boolean),
                      { shouldValidate: true },
                    );
                  }}
                />
                {errors[field] && (
                  <span className="error" role="alert">
                    {errors[field]?.message}
                  </span>
                )}
              </label>
            ))}
            {!personal && (
              <>
                <label className="field-label">
                  用餐人数
                  <input
                    type="number"
                    min={1}
                    max={20}
                    {...register("partySize", { valueAsNumber: true })}
                  />
                </label>
                <label className="field-label">
                  餐段
                  <select {...register("mealPeriod")}>
                    <option value="breakfast">早餐</option>
                    <option value="lunch">午餐</option>
                    <option value="dinner">晚餐</option>
                    <option value="lateNight">夜宵</option>
                  </select>
                </label>
                {errors.partySize && (
                  <p className="error" role="alert">
                    {errors.partySize.message}
                  </p>
                )}
                {errors.mealPeriod && (
                  <p className="error" role="alert">
                    {errors.mealPeriod.message}
                  </p>
                )}
              </>
            )}
            <fieldset>
              <legend>用餐场景</legend>
              <div className="chips">
                {["适合一人食", "适合聊天", "热乎"].map((tag) => (
                  <button
                    type="button"
                    key={tag}
                    aria-pressed={watch("softPreferences").includes(tag)}
                    onClick={() =>
                      setValue(
                        "softPreferences",
                        watch("softPreferences").includes(tag)
                          ? watch("softPreferences").filter((t) => t !== tag)
                          : [...watch("softPreferences"), tag],
                      )
                    }
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>其他菜系</legend>
              <div className="chips">
                {cuisines.slice(6).map((c) => (
                  <button
                    type="button"
                    key={c}
                    aria-pressed={chosen.includes(c)}
                    onClick={() => toggle("preferredFoods", c)}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>不想吃什么</legend>
              <div className="chips">
                {cuisines.map((c) => (
                  <button
                    type="button"
                    key={c}
                    aria-pressed={excluded.includes(c)}
                    onClick={() => toggle("excludedFoods", c)}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </fieldset>
            <p className="muted">POI 信息不能保证具体菜品的过敏安全。</p>
          </div>
        </SheetContent>
      </Sheet>
      {errors.root && (
        <p className="error" role="alert">
          {errors.root.message}
        </p>
      )}
      {Object.keys(errors).some((field) => field !== "root") && (
        <p className="error" role="alert">
          请检查预算上下限、搜索半径及是否有重复排除的菜系。
        </p>
      )}
      <Button
        type="submit"
        disabled={busy || isSubmitting}
        className="primary-full"
      >
        {busy || isSubmitting ? "正在处理…" : label}
      </Button>
    </form>
  );
}
