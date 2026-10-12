import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { SlidersHorizontal } from "lucide-react";
import {
  preferencesSchema, cuisines, isSearchRadius, type Preferences, type PreferencesSnapshot,
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
}: {
  initial: PreferencesSnapshot;
  onSubmit: (value: Preferences) => void;
  label: string;
  busy?: boolean;
}) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<Preferences>({
    resolver: zodResolver(preferencesSchema),
    defaultValues: {
      ...initial,
      radiusMeters: isSearchRadius(initial.radiusMeters) ? initial.radiusMeters : undefined,
    },
  });
  const radius = watch("radiusMeters"),
    chosen = watch("preferredCuisines"),
    excluded = watch("excludedCuisines");
  const toggle = (
    field: "preferredCuisines" | "excludedCuisines",
    item: string,
  ) => {
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
      onSubmit={handleSubmit((value) =>
        onSubmit({
          ...value,
          budgetPerPerson: {
            min: value.budgetPerPerson.min || null,
            max: value.budgetPerPerson.max || null,
          },
        }),
      )}
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
      </fieldset>
      <fieldset data-invalid={!!errors.radiusMeters || undefined}>
        <legend>搜索半径</legend>
        <RadiusOptions
          value={radius}
          onChange={(value) => setValue("radiusMeters", value, { shouldValidate: true, shouldDirty: true })}
          disabled={busy}
          invalid={!!errors.radiusMeters}
        />
        <p className="muted">以确认位置为中心的直线范围；补充说明中的距离也需使用这四档。</p>
        {!isSearchRadius(initial.radiusMeters) && !isSearchRadius(radius) && (
          <p className="warning-text">
            旧记录的半径为 {formatDistance(initial.radiusMeters)}，请重新选择搜索范围。
          </p>
        )}
      </fieldset>
      <fieldset>
        <legend>今天想吃什么</legend>
        <div className="chips">
          <button
            type="button"
            aria-pressed={!chosen.length}
            onClick={() => setValue("preferredCuisines", [])}
          >
            不限
          </button>
          {cuisines.slice(0, 6).map((c) => (
            <button
              type="button"
              key={c}
              aria-pressed={chosen.includes(c)}
              onClick={() => toggle("preferredCuisines", c)}
            >
              {c}
            </button>
          ))}
        </div>
      </fieldset>
      <label className="field-label">
        补充说明 <span>可选</span>
        <textarea
          placeholder="想吃热乎的，今天不太想吃面…"
          rows={3}
          {...register("requestText")}
        />
      </label>
      <Sheet>
        <SheetTrigger asChild>
          <Button type="button" variant="ghost" className="advanced">
            <SlidersHorizontal size={16} />
            更多条件 · 人数、场景与不想吃的
          </Button>
        </SheetTrigger>
        <SheetContent side="bottom" className="advanced-sheet">
          <SheetHeader>
            <SheetTitle>把这一餐，说得更具体</SheetTitle>
            <SheetDescription>
              条件只用于本次推荐，未知数据会明确提示。
            </SheetDescription>
          </SheetHeader>
          <div className="sheet-fields">
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
            <fieldset>
              <legend>用餐场景</legend>
              <div className="chips">
                {["适合一人食", "适合聊天", "热乎"].map((tag) => (
                  <button
                    type="button"
                    key={tag}
                    aria-pressed={watch("desiredTags").includes(tag)}
                    onClick={() =>
                      setValue(
                        "desiredTags",
                        watch("desiredTags").includes(tag)
                          ? watch("desiredTags").filter((t) => t !== tag)
                          : [...watch("desiredTags"), tag],
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
                    onClick={() => toggle("preferredCuisines", c)}
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
                    onClick={() => toggle("excludedCuisines", c)}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </fieldset>
            <label className="checkbox">
              <input type="checkbox" {...register("openNowPreferred")} />
              排除明确关闭的餐厅
            </label>
            <p className="muted">POI 信息不能保证具体菜品的过敏安全。</p>
          </div>
        </SheetContent>
      </Sheet>
      {Object.keys(errors).length > 0 && (
        <p className="error" role="alert">
          请检查预算上下限、搜索半径及是否有重复排除的菜系。
        </p>
      )}
      <Button type="submit" disabled={busy} className="primary-full">
        {busy ? "正在处理…" : label}
      </Button>
    </form>
  );
}
