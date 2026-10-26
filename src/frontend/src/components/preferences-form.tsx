import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { SlidersHorizontal } from "lucide-react";
import {
  preferencesSchema,
  cuisines,
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
  SheetDescription,
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
}: {
  initial: Preferences;
  onSubmit: (value: Preferences) => void | Promise<void>;
  onDraftChange?: (value: Preferences) => void;
  label: string;
  busy?: boolean;
  personal?: boolean;
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
    excludedFoods: initial.excludedFoods.join("，"),
  }));
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
    setValue(
      field,
      text.split(/[,，]/).map((value) => value.trim()).filter(Boolean),
      { shouldValidate: true, shouldDirty: true },
    );
  };
  const toggle = (field: "allowedFoods" | "excludedFoods", item: string) => {
    const current = watch(field);
    setFoodInput(
      field,
      (current.includes(item)
        ? current.filter((c) => c !== item)
        : [...current, item]).join("，"),
    );
  };
  const sourceNote = (field: LearnableField) => memory && (
    <div className="preference-source">
      <span>{memory.automatic.includes(field) ? "保存后恢复自动学习" :
        ({ manual: "手动固定", learned: "长期记忆", builtin: "系统默认" })[memory.sources[field]]}</span>
      {Object.hasOwn(memory.overrides, field) && (
        <button type="button" className="text-button" disabled={busy || isSubmitting}
          aria-label={`${({ budgetPerPerson: "预算", radiusMeters: "距离", requestText: "补充说明" })[field]}${memory.automatic.includes(field) ? "取消恢复" : "恢复自动学习"}`}
          onClick={() => memory.onRestore(field)}>
          {memory.automatic.includes(field) ? "取消恢复" : "恢复自动学习"}
        </button>
      )}
    </div>
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
      className="preference-form"
    >
      <fieldset>
        <legend>
          人均预算 <span>元 / 人</span>
        </legend>
        {sourceNote("budgetPerPerson")}
        <div className="budget-inputs">
          <label className="sr-only" htmlFor="budget-min">
            最低预算
          </label>
          <input
            disabled={memory?.automatic.includes("budgetPerPerson")}
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
            disabled={memory?.automatic.includes("budgetPerPerson")}
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
        {sourceNote("radiusMeters")}
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
        <p className="muted">以确认位置为中心的直线范围。</p>
      </fieldset>
      <fieldset>
        <legend>限定食物类型（任选其一）</legend>
        <div className="chips">
          <button
            type="button"
            aria-pressed={!chosen.length}
            onClick={() => setFoodInput("allowedFoods", "")}
          >
            不限
          </button>
          {cuisines.slice(0, 6).map((c) => (
            <button
              type="button"
              key={c}
              aria-pressed={chosen.includes(c)}
              disabled={chosen.length >= allowedFoodLimit && !chosen.includes(c)}
              onClick={() => toggle("allowedFoods", c)}
            >
              {c}
            </button>
          ))}
        </div>
      </fieldset>
      <label className="field-label">
        自由填写
        <input
          aria-label="限定食物类型"
          value={foodInputs.allowedFoods}
          placeholder="用逗号分隔，可自由填写菜系或菜品"
          onChange={(event) => setFoodInput("allowedFoods", event.target.value)}
        />
        <span className="muted">最多选择或填写 {allowedFoodLimit} 项，用逗号分隔。</span>
        {errors.allowedFoods && <span className="error" role="alert">{errors.allowedFoods.message}</span>}
      </label>
      <div>
      {sourceNote("requestText")}
      <label className="field-label">
        {personal ? "默认补充说明" : "补充说明"} <span>可选</span>
        <textarea
          disabled={memory?.automatic.includes("requestText")}
          placeholder="想吃热乎的，今天不太想吃面…"
          rows={3}
          maxLength={1000}
          {...register("requestText")}
        />
        <span className="muted">仅影响排序；必须满足的条件请在表单中设置。最多 1000 字。</span>
        {errors.requestText && <span className="error" role="alert">{errors.requestText.message}</span>}
      </label>
      </div>
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
                ? "保存常用条件，用于下次开始新的选餐。"
                : "条件只用于本次推荐，未知数据会明确提示。"}
            </SheetDescription>
          </SheetHeader>
          <div className="sheet-fields">
            <label className="field-label">
              排除的食物
              <input
                aria-label="排除的食物"
                name="excludedFoods"
                value={foodInputs.excludedFoods}
                placeholder="用逗号分隔，可填写菜系或菜品"
                onChange={(event) => setFoodInput("excludedFoods", event.target.value)}
              />
              {errors.excludedFoods && (
                <span className="error" role="alert">{errors.excludedFoods.message}</span>
              )}
            </label>
            {!personal && (
              <>
                <p className="muted">人数和餐段用于软排序参考；营业时间、座位及接待能力请向餐厅确认。</p>
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
              <legend>口味与场景（添加到补充说明）</legend>
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
              <legend>其他菜系</legend>
              <div className="chips">
                {cuisines.slice(6).map((c) => (
                  <button
                    type="button"
                    key={c}
                    aria-pressed={chosen.includes(c)}
                    onClick={() => toggle("allowedFoods", c)}
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
          请检查表单中的错误提示后再提交。
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
