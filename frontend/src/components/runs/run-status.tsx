import { Badge } from "@/components/ui/badge";
import type { AgentRun } from "@/lib/api/client";
import { cn } from "@/lib/utils";

const labels: Record<AgentRun["state"], string> = {
  QUEUED: "已排队",
  RUNNING: "检索与推理中",
  WAITING_APPROVAL: "等待审批",
  COMPLETED: "已完成",
  PARTIAL: "部分完成",
  FAILED: "运行失败",
  TIMED_OUT: "运行超时",
  CANCELLED: "已取消",
};

export function RunStatus({ state }: { state: AgentRun["state"] }) {
  const active = state === "QUEUED" || state === "RUNNING";
  const failed = state === "FAILED" || state === "TIMED_OUT" || state === "CANCELLED";
  return (
    <Badge className={cn(active && "animate-pulse", failed && "border-red-200 bg-red-50 text-red-700")}>
      {labels[state]}
    </Badge>
  );
}
