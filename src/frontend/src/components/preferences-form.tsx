import { useEffect, useState, type ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { SlidersHorizontal, ChevronRight } from "lucide-react";
import { BrandArcs, BrandMark } from "./brand";
import { cn } from "../lib/utils";
import {
  preferencesSchema,
  cuisines,
  excludedCuisineOptions,
  allowedFoodLimit,
  type Preferences,
  type AccountPreferences,
  type LearnableField,
} from "../lib/schemas";
import { RadiusOptions } from "./radius-options";
import { Button } from "./ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "./ui/sheet";
export function PreferencesForm({
  initial,
  onSubmit,
  onDraftChange,
  label,
  busy = false,
  personal = false,
  memory,
  children,
}: {
  initial: Preferences;
  onSubmit: (value: Preferences) => void | Promise<void>;
  onDraftChange?: (value: Preferences) => void;
  label: string;
  busy?: boolean;
  personal?: boolean;
  children?: ReactNode;
  memory?: {
    sources: AccountPreferences["sources"];
    overrides: AccountPreferences["overrides"];
    automatic: LearnableField[];
    onRestore: (field: LearnableField) => void;
  };
}) {
  const [advanced, setAdvanced] = useState(false);
  const [foodInputs, setFoodInputs] = useState(() => ({
    allowedFoods: initial.allowedFoods.join("，"),
    excludedFoods: initial.excludedFoods.filter((value) => !excludedCuisineOptions.includes(value)).join("，"),
  }));
  const [showOtherCuisine, setShowOtherCuisine] = useState(() =>
    initial.excludedFoods.some((value) => !excludedCuisineOptions.includes(value)),
  );
  const {
    control,
    register,
    setError,
    clearErrors,
    handleSubmit,
    watch,
    subscribe,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<Preferences, unknown, Preferences>({
    resolver: zodResolver(preferencesSchema),
    defaultValues: initial,
  });
  useEffect(() => {
    if (!onDraftChange) return;
    return subscribe({
      formState: { values: true },
      callback: ({ values }) => onDraftChange(values),
    });
  }, [subscribe, onDraftChange]);
  const radius = watch("radiusMeters"),
    chosen = watch("allowedFoods"),
    excluded = watch("excludedFoods");
  const setFoodInput = (field: keyof typeof foodInputs, text: string) => {
    setFoodInputs((current) => ({ ...current, [field]: text }));
    const names = text.split(/[,，]/).map((value) => value.trim()).filter(Boolean);
    setValue(
      field,
      field === "excludedFoods"
        ? [...new Set([...watch("excludedFoods").filter((value) => excludedCuisineOptions.includes(value)), ...names])]
        : names,
      { shouldValidate: true, shouldDirty: true },
    );
  };
  const toggleAllowed = (item: string) => {
    const current = watch("allowedFoods");
    setFoodInput(
      "allowedFoods",
      (current.includes(item)
        ? current.filter((c) => c !== item)
        : [...current, item]).join("，"),
    );
  };
  const toggleExcludedCuisine = (item: string) => {
    const current = watch("excludedFoods");
    const removing = current.includes(item);
    setValue("excludedFoods", removing ? current.filter((value) => value !== item) : [...current, item],
      { shouldValidate: true, shouldDirty: true });
    if (removing) setFoodInputs((inputs) => ({ ...inputs,
      excludedFoods: inputs.excludedFoods.split(/[,，]/).filter((value) => value.trim() !== item).join("，"),
    }));
  };
  const toggleOtherCuisine = () => {
    if (showOtherCuisine) {
      setFoodInputs((inputs) => ({ ...inputs, excludedFoods: "" }));
      setValue("excludedFoods", watch("excludedFoods").filter((value) => excludedCuisineOptions.includes(value)),
        { shouldValidate: true, shouldDirty: true });
    }
    setShowOtherCuisine((visible) => !visible);
  };
  const sourceNote = (field: LearnableField) => memory && (
    <span className="preference-source">
      <span>{memory.automatic.includes(field) ? "保存后恢复自动学习" :
        ({ manual: "手动固定", learned: "长期记忆", builtin: "系统默认" })[memory.sources[field]]}</span>
      {Object.hasOwn(memory.overrides, field) && (
        <button type="button" className="text-button" disabled={busy || isSubmitting}
          aria-label={`${({ budgetPerPerson: "预算", radiusMeters: "距离", requestText: "补充说明" })[field]}${memory.automatic.includes(field) ? "取消恢复" : "恢复自动学习"}`}
          onClick={() => memory.onRestore(field)}>
          {memory.automatic.includes(field) ? "取消恢复" : "恢复自动学习"}
        </button>
      )}
    </span>
  );
  const foodInput = (
    <label className="food-input">
      <span className="sr-only">限定食物类型</span>
      <input
        aria-label="限定食物类型"
        value={foodInputs.allowedFoods}
        placeholder="填写菜系或菜品"
        aria-describedby="food-limit"
        aria-invalid={!!errors.allowedFoods}
        onChange={(event) => setFoodInput("allowedFoods", event.target.value)}
      />
    </label>
  );
  const foodSection = (
    <section className={cn("food-section", { "page-hero": !personal })}>
      {!personal && <><BrandArcs /><h1>想吃什么？</h1></>}
      <fieldset>
        <legend className={personal ? undefined : "sr-only"}>限定食物类型 <span>任选其一</span></legend>
        <div className="food-controls">
          {!personal && foodInput}
          <div className="chips">
            <button type="button" aria-pressed={!chosen.length} onClick={() => setFoodInput("allowedFoods", "")}>
              {!chosen.length && <BrandMark />}不限
            </button>
            {(personal ? cuisines.slice(0, 3) : ["家常菜", "面食", "火锅", "日料", "轻食"]).map((c) => (
              <button
                type="button"
                key={c}
                aria-pressed={chosen.includes(c)}
                disabled={chosen.length >= allowedFoodLimit && !chosen.includes(c)}
                onClick={() => toggleAllowed(c)}
              >
                {chosen.includes(c) && <BrandMark />}{c}
              </button>
            ))}
          </div>
          {personal && foodInput}
          <p id="food-limit" className={cn("muted", "food-limit", { "sr-only": !personal })}>最多 {allowedFoodLimit} 项，用逗号分隔。</p>
          {errors.allowedFoods && <p className="error" role="alert">{errors.allowedFoods.message}</p>}
        </div>
      </fieldset>
    </section>
  );
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
      className={cn("preference-form", personal ? "personal-preferences" : "home-preferences")}
    >
      {!personal && foodSection}
      <fieldset className="budget-section">
        <legend>
          人均预算 <span>元 / 人</span>
        </legend>
        <div className="budget-inputs">
          <label className="budget-field" htmlFor="budget-min">
            <span className="sr-only">最低预算</span>
            <input
              disabled={memory?.automatic.includes("budgetPerPerson")}
              id="budget-min"
              inputMode="decimal"
              placeholder="不限"
              aria-invalid={!!(errors.budgetPerPerson?.min || errors.budgetPerPerson?.message)}
              {...register("budgetPerPerson.min")}
            />
            {!personal && <span className="budget-caption" aria-hidden="true">最低</span>}
          </label>
          <span>—</span>
          <label className="budget-field" htmlFor="budget-max">
            <span className="sr-only">最高预算</span>
            <input
              disabled={memory?.automatic.includes("budgetPerPerson")}
              id="budget-max"
              inputMode="decimal"
              placeholder="不限"
              aria-invalid={!!(errors.budgetPerPerson?.max || errors.budgetPerPerson?.message)}
              {...register("budgetPerPerson.max")}
            />
            {!personal && <span className="budget-caption" aria-hidden="true">最高</span>}
          </label>
        </div>
        {sourceNote("budgetPerPerson")}
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
        <legend className="field-heading">搜索半径{sourceNote("radiusMeters")}</legend>
        <RadiusOptions
          value={radius}
          onChange={(value) =>
            setValue("radiusMeters", value, {
              shouldValidate: true,
              shouldDirty: true,
            })
          }
          disabled={busy || isSubmitting || memory?.automatic.includes("radiusMeters")}
          invalid={!!errors.radiusMeters}
        />
        {errors.radiusMeters && (
          <p className="error" role="alert">
            {errors.radiusMeters.message}
          </p>
        )}
      </fieldset>
      {personal && foodSection}
      <div className="note-section">
        <div className="field-heading">
          <label className="field-label" htmlFor="request-text">
            {personal ? "默认补充说明" : "补充说明"} {!personal && <span>可选</span>}
          </label>
          {sourceNote("requestText")}
        </div>
        <textarea
          id="request-text"
          disabled={memory?.automatic.includes("requestText")}
          placeholder="想吃热乎的，今天不太想吃面…"
          rows={2}
          aria-invalid={!!errors.requestText}
          maxLength={1000}
          {...register("requestText")}
        />
        {errors.requestText && <p className="error" role="alert">{errors.requestText.message}</p>}
      </div>
      <Sheet open={advanced} onOpenChange={setAdvanced}>
        <SheetTrigger asChild>
          <Button type="button" variant="ghost" className="advanced">
            <SlidersHorizontal size={16} />
            {personal ? "更多偏好 · 口味与不想吃的菜系" : "更多条件"}
            <ChevronRight />
          </Button>
        </SheetTrigger>
        <SheetContent side="bottom" className="advanced-sheet" aria-describedby={undefined}>
          <SheetHeader>
            <SheetTitle>把这一餐，说得更具体</SheetTitle>
          </SheetHeader>
          <div className="sheet-fields">
            <fieldset data-invalid={!!errors.excludedFoods || undefined}>
              <legend>不想吃的菜系</legend>
              <div className="cuisine-options">
                {excludedCuisineOptions.map((cuisine) => (
                  <label key={cuisine}>
                    <input type="checkbox" checked={excluded.includes(cuisine)}
                      disabled={busy || isSubmitting || (excluded.length >= 12 && !excluded.includes(cuisine))}
                      onChange={() => toggleExcludedCuisine(cuisine)} />
                    {cuisine}
                  </label>
                ))}
                <label>
                  <input type="checkbox" checked={showOtherCuisine}
                    disabled={busy || isSubmitting || (excluded.length >= 12 && !showOtherCuisine)}
                    onChange={toggleOtherCuisine} />
                  其他菜系
                </label>
              </div>
              {showOtherCuisine && (
                <label className="field-label">
                  其他不想吃的菜系
                  <input aria-label="其他不想吃的菜系" autoFocus
                    value={foodInputs.excludedFoods}
                    placeholder="输入菜系名称，用逗号分隔"
                    onChange={(event) => setFoodInput("excludedFoods", event.target.value)} />
                </label>
              )}
              {errors.excludedFoods && (
                <span className="error" role="alert">{errors.excludedFoods.message}</span>
              )}
            </fieldset>
            {!personal && (
              <>
                <label className="field-label">
                  用餐人数
                  <Controller
                    name="partySize"
                    control={control}
                    render={({ field }) => (
                      <input
                        {...field}
                        type="number"
                        min={1}
                        max={20}
                        value={Number.isNaN(field.value) ? "" : field.value}
                        onChange={(event) => field.onChange(event.target.valueAsNumber)}
                      />
                    )}
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
                  <p className="error" role="alert">{errors.partySize.message}</p>
                )}
                {errors.mealPeriod && (
                  <p className="error" role="alert">{errors.mealPeriod.message}</p>
                )}
              </>
            )}
            <fieldset>
              <legend>口味与场景</legend>
              <div className="chips">
                {["适合一人食", "适合聊天", "热乎"].map((tag) => (
                  <button
                    type="button"
                    key={tag}
                    onClick={() => setValue("requestText", [watch("requestText"), tag].filter(Boolean).join("；"), { shouldDirty: true, shouldValidate: true })}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>更多限定类型</legend>
              <div className="chips">
                {cuisines.map((c) => (
                  <button
                    type="button"
                    key={c}
                    aria-pressed={chosen.includes(c)}
                    onClick={() => toggleAllowed(c)}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </fieldset>
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
          请检查表单中的错误提示后再提交。
        </p>
      )}
      {children}
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
