import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, LoaderCircle } from "lucide-react";
import { ApiError, errorMessage, request } from "../lib/api";
import {
  acceptRecommendation,
  completeSelection,
  isDiscardedRun,
  readRecommendation,
  refreshCurrentRecommendation,
} from "../lib/recommendations";
import { choiceResultSchema, runSchema, type Run } from "../lib/schemas";
import { useDraft } from "../lib/store";
import { subscribe } from "../lib/stream";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";

const submissionWaitMs = 15_000;

type Step = { node: string; label: string; done: boolean };

export function BackgroundActivity() {
  const { pathname } = useLocation();
  const client = useQueryClient();
  const job = useDraft((state) => state.job);
  const runId = useDraft((state) => state.runId);
  const [streamingRunId, setStreamingRunId] = useState<string | null>(null);
  const [progress, setProgress] = useState<{
    runId: string;
    steps: Step[];
    error: string;
  }>({ runId: "", steps: [], error: "" });
  const query = useQuery({
    queryKey: ["run", runId],
    queryFn: ({ signal }) => readRecommendation(client, runId!, signal),
    enabled: !!runId && !isDiscardedRun(client, runId),
    refetchInterval: (q) =>
      streamingRunId !== runId && ["pending", "running"].includes(q.state.data?.status ?? "")
        ? 2000
        : false,
    refetchIntervalInBackground: true,
    retry: false,
  });
  const run = query.data;
  const active = !!run && ["pending", "running"].includes(run.status);

  useEffect(() => {
    if (!job || job.status !== "submitting") return;
    const controller = new AbortController();
    const current = () =>
      !controller.signal.aborted && useDraft.getState().job === job;
    const timer = setTimeout(() => {
      if (!current()) return;
      controller.abort();
      // Aborting cannot undo server acceptance; retain the body and key for a confirming retry.
      useDraft.getState().setJob({
        ...job,
        status: "failed",
        error: "500 Error：提交确认超时，任务可能已受理，请重新确认结果。",
      });
    }, submissionWaitMs);
    const submit = async () => {
      if (job.kind === "recommendation") {
        const accepted = await request(
          job.path,
          job.body,
          "POST",
          job.key,
          controller.signal,
          runSchema,
        );
        if (!current()) return;
        acceptRecommendation(client, accepted, job.runId);
        useDraft.getState().setRunId(accepted.decisionRunId);
        useDraft.getState().setJob(null);
      } else {
        await request(
          job.path,
          job.body,
          "POST",
          job.key,
          controller.signal,
          choiceResultSchema,
        );
        if (!current()) return;
        useDraft.getState().setJob({ ...job, status: "saved" });
        if (job.runId) await completeSelection(client, job.runId);
      }
    };
    void submit()
      .catch((error: unknown) => {
        if (!current()) return;
        useDraft.getState().setJob({
          ...job,
          status: error instanceof ApiError && (
            (error.status >= 400 && error.status < 500) || error.code === "QUEUE_FULL"
          )
            ? "rejected" : "failed",
          error: error instanceof Error ? error.message : "提交失败",
        });
        if (job.runId)
          void client.invalidateQueries({ queryKey: ["run", job.runId] });
      })
      .finally(() => clearTimeout(timer));
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [job, client]);

  // Keep one subscription attempt per active run; a failed stream leaves polling in charge.
  useEffect(() => {
    if (!runId || !active) return;
    const controller = new AbortController();
    const current = () =>
      !controller.signal.aborted &&
      useDraft.getState().runId === runId &&
      !isDiscardedRun(client, runId);
    let idleTimer: ReturnType<typeof setTimeout>;
    const waitForActivity = () => {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        if (!current()) return;
        setStreamingRunId(null);
        setProgress((previous) => ({
          runId, steps: previous.runId === runId ? previous.steps : [],
          error: "500 Error：进度连接超时，已改为查询结果。",
        }));
        controller.abort();
      }, 35_000);
    };
    waitForActivity();
    void subscribe(runId, controller.signal, (event) => {
      if (!current()) return;
      setStreamingRunId(runId);
      waitForActivity();
      if (event.type === "runStarted") setProgress({ runId, steps: [], error: "" });
      if (["runStarted", "nodeStarted", "nodeCompleted"].includes(event.type))
        client.setQueryData<Run>(["run", runId], (previous) =>
          previous?.status === "pending" ? { ...previous, status: "running" } : previous,
        );
      if (event.type === "nodeStarted" || event.type === "nodeCompleted") {
        setProgress((previous) => {
          const steps = previous.runId === runId ? previous.steps : [];
          const step = steps.find((item) => item.node === event.node);
          return {
            runId,
            error: "",
            steps:
              event.type === "nodeStarted"
                ? [
                    ...steps.filter((item) => item.node !== event.node),
                    { node: event.node, label: event.label, done: false },
                  ]
                : [
                    ...steps.filter((item) => item.node !== event.node),
                    {
                      node: event.node,
                      label: step?.label ?? "正在处理推荐",
                      done: true,
                    },
                  ],
          };
        });
      } else if (event.type === "result") {
        client.setQueryData<Run>(["run", runId], (previous) =>
          previous?.choice ? previous : event.data,
        );
      } else if (event.type === "runFailed") {
        setProgress((previous) => ({
          runId,
          steps: previous.runId === runId ? previous.steps : [],
          error: errorMessage(event.error.code, event.error.message),
        }));
        void client.invalidateQueries({ queryKey: ["run", runId] });
      }
    }).catch((error: unknown) => {
      if (current()) {
        setStreamingRunId(null);
        setProgress((previous) => ({
          runId,
          steps: previous.runId === runId ? previous.steps : [],
          error: error instanceof ApiError && ["USER_STREAM_LIMIT_REACHED", "STREAM_CAPACITY_REACHED"].includes(error.code)
            ? "实时进度连接已满，已改为查询结果。"
            : error instanceof ApiError ? error.message : "500 Error：进度连接中断，已改为查询结果。",
        }));
      }
    }).finally(() => clearTimeout(idleTimer));
    return () => { clearTimeout(idleTimer); controller.abort(); };
  }, [runId, active, client]);

  const sessionId = run?.discoverySessionId;
  useEffect(() => {
    if (
      query.error instanceof ApiError &&
      query.error.code === "RUN_SUPERSEDED" &&
      sessionId
    ) {
      void refreshCurrentRecommendation(client, sessionId).catch(
        (error: unknown) => {
          if (useDraft.getState().runId === runId)
            setProgress({
              runId: runId ?? "",
              steps: [],
              error: error instanceof Error ? error.message : "读取失败",
            });
        },
      );
    }
  }, [query.error, sessionId, runId, client]);

  if (!job && !runId) return null;
  const submitting = job?.status === "submitting";
  const saved =
    (job?.kind === "choice" && job.status === "saved") || !!run?.choice;
  const pending = submitting || active;
  const steps = progress.runId === runId ? progress.steps : [];
  const error =
    job?.error ||
    (progress.runId === runId &&
    (active || run?.status === "failed" || query.isError)
      ? progress.error
      : "") ||
    query.error?.message ||
    (run?.status === "failed"
      ? errorMessage(run.errorCode ?? "RUN_FAILED", "推荐未完成，请重试。")
      : "");
  const target = saved ? `/decision-runs/${job?.runId ?? runId}` : "/discover";
  const completed = run?.status === "completed" && !pending && !error && (!job || job.status === "saved");
  if (pathname === target && completed) return null;
  const title = submitting
    ? job.kind === "choice"
      ? "正在保存选择…"
      : "正在提交选餐任务…"
    : job?.status === "rejected"
      ? "任务未受理，请查看提示后重试"
      : job?.status === "failed"
        ? "提交未完成，请重试确认"
        : saved
          ? "选择已保存"
          : query.error
            ? "推荐状态读取失败"
            : run?.status === "failed"
              ? "推荐未完成"
              : active
                ? run?.status === "pending"
                  ? "选餐任务已排队"
                  : "正在推荐餐厅"
                : run
                  ? "推荐已完成"
                  : "正在读取任务状态…";
  return (
    <aside className={cn("background-activity", { "activity-compact": completed })} aria-label="选餐任务">
      <div className="activity-heading" role="status">
        {pending ? (
          <LoaderCircle size={18} className="spin" />
        ) : (
          <Check size={18} />
        )}
        <strong>{title}</strong>
      </div>
      {pending && (
        <p className="muted">可以继续浏览其他页面，完成后在这里查看结果。</p>
      )}
      {active && steps.length > 0 && (
        <ol className="activity-steps" aria-label="推荐进度">
          {steps.slice(-3).map((step) => (
            <li key={step.node}>
              {step.done ? (
                <Check size={14} />
              ) : (
                <LoaderCircle size={14} className="spin" />
              )}
              {step.label}
            </li>
          ))}
        </ol>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="activity-actions">
        {job && job.status !== "saved" && (
          <Button
            variant="outline"
            onClick={() =>
              useDraft
                .getState()
                .setJob({ ...job, status: "submitting", error: null })
            }
          >
            {job.status === "failed" || job.status === "rejected" ? "重试提交" : "重新确认状态"}
          </Button>
        )}
        {runId && (
          <Button variant="outline" asChild>
            <Link to={target}>
              {saved
                ? "查看已选餐厅"
                : pending
                  ? "查看推荐进度"
                  : "查看推荐结果"}
            </Link>
          </Button>
        )}
        {query.isError && (
          <Button variant="outline" onClick={() => void query.refetch()}>
            查询结果
          </Button>
        )}
      </div>
    </aside>
  );
}
