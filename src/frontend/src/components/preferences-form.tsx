import { useEffect, useState, type ReactNode } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Check, SlidersHorizontal, ChevronRight, ChevronDown } from "lucide-react";
import { cn, formatBudget, formatDistance } from "../lib/utils";
import { useDesktop } from "../lib/use-desktop";
import { DesktopPageHeader } from "./desktop-page-header";
import { Brand, PageHero } from "./brand";
import {
  preferencesSchema,
  cuisines,
  tasteOptions,
  integerBudget,
  allowedFoodLimit,
  type Preferences,
} from "../lib/schemas";
import { RadiusOptions } from "./radius-options";
import { BudgetRange } from "./budget-range";
import { Button } from "./ui/button";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "./ui/sheet";

type FoodField = "allowedFoods" | "excludedFoods";

function foodNames(text: string): string[] {
  return text.split(/[,，]/).map((value) => value.trim()).filter(Boolean);
}

export function PreferencesForm({
  initial,
  onSubmit,
  onDraftChange,
  label,
  busy = false,
  personal = false,
  headingAction,
  children,
}: {
  initial: Preferences;
  onSubmit: (value: Preferences) => void | Promise<void>;
  onDraftChange?: (value: Preferences) => void;
  label: string;
  busy?: boolean;
  personal?: boolean;
  headingAction?: ReactNode;
  children?: ReactNode;
}) {
  const desktop = useDesktop();
  const [advanced, setAdvanced] = useState(false);
  const [allowedInput, setAllowedInput] = useState(initial.allowedFoods.join("，"));
  const [otherFoods, setOtherFoods] = useState(() => ({
    allowedFoods: initial.allowedFoods.filter((value) => !cuisines.includes(value)).join("，"),
    excludedFoods: initial.excludedFoods.filter((value) => !cuisines.includes(value)).join("，"),
  }));
  const [showOtherCuisine, setShowOtherCuisine] = useState({
    allowedFoods: !!otherFoods.allowedFoods, excludedFoods: !!otherFoods.excludedFoods,
  });
  const [otherTaste, setOtherTaste] = useState(() =>
    initial.requestText.split("；").filter((value) => value && !tasteOptions.includes(value)).join("；"),
  );
  const [showOtherTaste, setShowOtherTaste] = useState(!!otherTaste);
  const initialMinimum = integerBudget(initial.budgetPerPerson.min || "1");
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
    defaultValues: {
      ...initial,
      budgetPerPerson: {
        min: initialMinimum === "0" ? "1" : initialMinimum,
        max: initial.budgetPerPerson.max ? integerBudget(initial.budgetPerPerson.max) : null,
      },
    },
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
    requestText = watch("requestText");
  const disabled = busy || isSubmitting;
  const updateFoods = (field: FoodField, values: string[]) => {
    setValue(field, values, { shouldValidate: true, shouldDirty: true });
    if (field === "allowedFoods") setAllowedInput(values.join("，"));
  };
  const setAllowedText = (text: string) => {
    const names = foodNames(text);
    const custom = names.filter((value) => !cuisines.includes(value)).join("，");
    setValue("allowedFoods", names, { shouldValidate: true, shouldDirty: true });
    setAllowedInput(text);
    setOtherFoods((current) => ({ ...current, allowedFoods: custom }));
    if (custom) setShowOtherCuisine((current) => ({ ...current, allowedFoods: true }));
  };
  const toggleFood = (field: FoodField, item: string) => {
    const current = watch(field);
    updateFoods(field, current.includes(item) ? current.filter((value) => value !== item) : [...current, item]);
    if (current.includes(item)) setOtherFoods((inputs) => ({
      ...inputs, [field]: foodNames(inputs[field]).filter((value) => value !== item).join("，"),
    }));
  };
  const toggleOtherCuisine = (field: FoodField) => {
    if (showOtherCuisine[field]) {
      setOtherFoods((current) => ({ ...current, [field]: "" }));
      updateFoods(field, watch(field).filter((value) => cuisines.includes(value)));
    }
    setShowOtherCuisine((current) => ({ ...current, [field]: !current[field] }));
  };
  const cuisineOptions = (field: FoodField) => {
    const selected = watch(field);
    const limit = field === "allowedFoods" ? allowedFoodLimit : 12;
    return <>
      <div className="chips">
        <button type="button" aria-pressed={!selected.length} disabled={disabled} onClick={() => {
          updateFoods(field, []);
          setOtherFoods((current) => ({ ...current, [field]: "" }));
          setShowOtherCuisine((current) => ({ ...current, [field]: false }));
        }}>不限</button>
        {cuisines.map((cuisine) => <button type="button" key={cuisine}
          aria-pressed={selected.includes(cuisine)}
          disabled={disabled || (selected.length >= limit && !selected.includes(cuisine))}
          onClick={() => toggleFood(field, cuisine)}>
          {selected.includes(cuisine) && <Check aria-hidden="true" />}{cuisine}
        </button>)}
        <button type="button" aria-pressed={showOtherCuisine[field]}
          disabled={disabled || (selected.length >= limit && !showOtherCuisine[field])}
          onClick={() => toggleOtherCuisine(field)}>其他</button>
      </div>
      {showOtherCuisine[field] && <label className="field-label other-condition">
        {field === "allowedFoods" ? "其他限定类型" : "其他不想吃的菜系"}
        <input aria-label={field === "allowedFoods" ? "其他限定类型" : "其他不想吃的菜系"}
          disabled={disabled} value={otherFoods[field]} placeholder="输入菜系或菜品，用逗号分隔"
          onChange={(event) => {
            const text = event.target.value;
            setOtherFoods((current) => ({ ...current, [field]: text }));
            updateFoods(field, [...new Set([
              ...watch(field).filter((value) => cuisines.includes(value)), ...foodNames(text),
            ])]);
          }} />
      </label>}
    </>;
  };
  const foodInput = (
    <label className="food-input">
      <span className="sr-only">限定食物类型</span>
      <input
        aria-label="限定食物类型"
        value={allowedInput}
        placeholder="填写菜系或菜品"
        aria-describedby="food-limit"
        aria-invalid={!!errors.allowedFoods}
        onChange={(event) => setAllowedText(event.target.value)}
      />
    </label>
  );
  const foodSection = (
    <section className="food-section">
      <fieldset>
        <legend>
          {personal || desktop ? "限定食物类型" : "想吃什么"} {desktop && <span>最多选择 {allowedFoodLimit} 项</span>}
        </legend>
        <div className="food-controls">
          {personal || desktop ? cuisineOptions("allowedFoods") : <>
            <div className="chips">
            {[...new Set(["家常菜", "面食", "饺子", "轻食", ...chosen])].map((c) => (
              <button
                type="button"
                key={c}
                aria-pressed={chosen.includes(c)}
                disabled={disabled || (chosen.length >= allowedFoodLimit && !chosen.includes(c))}
                onClick={() => toggleFood("allowedFoods", c)}
              >
                {chosen.includes(c) && <Check aria-hidden="true" />}{c}
              </button>
            ))}
          </div>
          </>}
          <p id="food-limit" className={cn("muted", "food-limit", { "sr-only": !personal || desktop })}>最多选择 {allowedFoodLimit} 项。</p>
          {errors.allowedFoods && <p className="error" role="alert">{errors.allowedFoods.message}</p>}
        </div>
      </fieldset>
    </section>
  );
  const advancedFields = (
    <div className="sheet-fields">
      {!personal && !desktop && <fieldset data-invalid={!!errors.allowedFoods || undefined}>
        <legend>更多限定类型</legend>
        {foodInput}
        {cuisineOptions("allowedFoods")}
        {errors.allowedFoods && <p className="error" role="alert">{errors.allowedFoods.message}</p>}
      </fieldset>}
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
      <fieldset className="taste-section">
        <legend>口味与场景</legend>
        <div className="chips">
          {tasteOptions.map((tag) => (
            <button
              type="button"
              key={tag}
              aria-pressed={requestText.split("；").includes(tag)}
              disabled={disabled}
              onClick={() => {
                const current = requestText.split("；").filter(Boolean);
                setValue("requestText", (current.includes(tag) ? current.filter((value) => value !== tag) : [...current, tag]).join("；"),
                  { shouldDirty: true, shouldValidate: true });
              }}
            >
              {tag}
            </button>
          ))}
          <button type="button" aria-pressed={showOtherTaste}
            disabled={disabled}
            onClick={() => {
              if (showOtherTaste) {
                setOtherTaste("");
                setValue("requestText", requestText.split("；").filter((value) => tasteOptions.includes(value)).join("；"),
                  { shouldDirty: true, shouldValidate: true });
              }
              setShowOtherTaste((visible) => !visible);
            }}>其他</button>
        </div>
        {showOtherTaste && <label className="field-label other-condition">
          其他口味与场景
          <input aria-label="其他口味与场景" value={otherTaste} maxLength={1000}
            disabled={disabled}
            placeholder="填写其他口味或用餐场景"
            onChange={(event) => {
              const text = event.target.value;
              setOtherTaste(text);
              setValue("requestText", [
                ...requestText.split("；").filter((value) => tasteOptions.includes(value)), text,
              ].filter(Boolean).join("；"), { shouldDirty: true, shouldValidate: true });
            }} />
        </label>}
        {errors.requestText && <p className="error" role="alert">{errors.requestText.message}</p>}
      </fieldset>
      <fieldset className="excluded-foods-section" data-invalid={!!errors.excludedFoods || undefined}>
        <legend>不想吃的菜系</legend>
        {cuisineOptions("excludedFoods")}
        {errors.excludedFoods && <p className="error" role="alert">{errors.excludedFoods.message}</p>}
      </fieldset>
    </div>
  );
  const submitButton = <Button type="submit" disabled={disabled} className="primary-full">
    {disabled ? "正在处理…" : label}
  </Button>;
  return (
    <form
      onChange={() => clearErrors("root")}
      onSubmit={handleSubmit(async (value) => {
        clearErrors();
        try {
          const budget = { ...value.budgetPerPerson, min: value.budgetPerPerson.min ?? "1" };
          setValue("budgetPerPerson", budget);
          await onSubmit({
            ...value,
            budgetPerPerson: budget,
          });
        } catch (error) {
          setError("root", {
            message: error instanceof Error ? error.message : "提交失败",
          });
        }
      })}
      className={cn("preference-form", personal ? "personal-preferences" : "home-preferences")}
    >
      {desktop && !personal && <DesktopPageHeader title="想吃什么？" description="从附近出发，选一顿合心意的。" />}
      {!desktop && !personal && <PageHero className="home-header">
        <div className="mobile-brand-row"><Brand />{headingAction}</div>
        <h1>想吃什么？</h1>
      </PageHero>}
      <div className={desktop ? "desktop-meal-layout" : "mobile-form-layout"}>
        <div className={desktop ? "desktop-form-fields" : "mobile-form-fields"}>
          <div className="financial-fields">
            <fieldset className="budget-section">
              <legend>
                人均预算 <span>元 / 人</span>
              </legend>
              <Controller name="budgetPerPerson" control={control} render={({ field }) => (
                <BudgetRange value={field.value} onChange={field.onChange}
                  disabled={disabled}
                  invalid={!!errors.budgetPerPerson} />
              )} />
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
              <legend className="field-heading">搜索范围</legend>
              <RadiusOptions
                value={radius}
                onChange={(value) =>
                  setValue("radiusMeters", value, {
                    shouldValidate: true,
                    shouldDirty: true,
                  })
                }
                disabled={disabled}
                invalid={!!errors.radiusMeters}
              />
              {errors.radiusMeters && (
                <p className="error" role="alert">
                  {errors.radiusMeters.message}
                </p>
              )}
            </fieldset>
          </div>
          {foodSection}
          <div className="note-section">
            <div className="field-heading">
              <label className="field-label" htmlFor="request-text">
                {personal ? "默认补充说明" : "补充说明"} {!personal && <span>可选</span>}
              </label>
            </div>
            <textarea
              id="request-text"
              placeholder="想吃热乎的，今天不太想吃面…"
              rows={2}
              aria-invalid={!!errors.requestText}
              maxLength={1000}
              {...register("requestText", { onChange: (event) => {
                const custom = (event.target.value as string).split("；")
                  .filter((value) => value && !tasteOptions.includes(value)).join("；");
                setOtherTaste(custom);
                if (custom) setShowOtherTaste(true);
              } })}
            />
            {errors.requestText && <p className="error" role="alert">{errors.requestText.message}</p>}
          </div>
          {desktop && personal ? advancedFields : desktop ? <details className="desktop-advanced">
            <summary><SlidersHorizontal size={17} />{personal ? "更多偏好 · 口味与不想吃的菜系" : "更多条件"}<ChevronDown size={17} /></summary>
            {advancedFields}
          </details> : <Sheet open={advanced} onOpenChange={setAdvanced}>
            <SheetTrigger asChild>
              <Button type="button" variant="ghost" className="advanced">
                <SlidersHorizontal size={16} />
                {personal ? "更多偏好 · 口味与不想吃的菜系" : "更多条件"}
                <ChevronRight />
              </Button>
            </SheetTrigger>
            <SheetContent side="bottom" className="advanced-sheet" aria-describedby={undefined}>
              <SheetTitle className="sr-only">补充条件</SheetTitle>
              {advancedFields}
            </SheetContent>
          </Sheet>}
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
          {desktop && personal && submitButton}
        </div>
        {desktop && !personal && <aside className="meal-summary" aria-label="本次选餐">
          <h2>本次选餐</h2>
          <div className="meal-origin">{headingAction}</div>
          <dl>
            <div><dt>食物类型</dt><dd>{chosen.length ? chosen.join("、") : "不限"}</dd></div>
            <div><dt>人均预算</dt><dd>{formatBudget(watch("budgetPerPerson")).replace("人均 ", "")}</dd></div>
            <div><dt>搜索范围</dt><dd>{formatDistance(radius)} 内</dd></div>
            <div><dt>用餐安排</dt><dd>{({ breakfast: "早餐", lunch: "午餐", dinner: "晚餐", lateNight: "夜宵" })[watch("mealPeriod")]} · {watch("partySize")} 人</dd></div>
          </dl>
          {submitButton}
        </aside>}
      </div>
      {!desktop && submitButton}
    </form>
  );
}
