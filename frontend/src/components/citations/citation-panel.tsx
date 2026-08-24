"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { BookOpenText, ExternalLink, FileText, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useCitationStore } from "./citation-store";

const supportLabels = {
  SUPPORTED: "完整支持",
  PARTIAL: "部分支持",
  CONFLICTED: "来源冲突",
} as const;

export function CitationPanel() {
  const selected = useCitationStore((state) => state.selected);
  const clear = useCitationStore((state) => state.clear);

  return (
    <Dialog.Root open={Boolean(selected)} onOpenChange={(open) => !open && clear()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#172033]/30" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-y-auto border-l border-[#d8dee8] bg-white p-7 shadow-2xl sm:p-9">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-[#324b6b]">
                <BookOpenText className="size-4" aria-hidden="true" />引用详情
              </p>
              <Dialog.Title className="mt-3 text-2xl font-semibold tracking-tight">
                {selected?.source.title ?? "来源"}
              </Dialog.Title>
              <Dialog.Description className="mt-2 text-sm leading-6 text-[#647087]">
                核对答案结论与当前授权来源的定位信息。
              </Dialog.Description>
            </div>
            <Dialog.Close className="grid size-9 shrink-0 place-items-center rounded-md text-[#647087] hover:bg-[#eef1f5]" aria-label="关闭引用详情">
              <X className="size-5" />
            </Dialog.Close>
          </div>

          {selected ? (
            <div className="mt-8 space-y-6">
              <section className="rounded-md border border-[#d8dee8] bg-[#f8f9fb] p-5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-semibold text-[#647087]">证据支持状态</span>
                  <Badge>{supportLabels[selected.supportStatus]}</Badge>
                </div>
                <p className="mt-4 text-sm font-medium leading-6">{selected.claimLocator}</p>
              </section>

              <dl className="grid gap-5 text-sm">
                <div>
                  <dt className="text-xs font-semibold text-[#778399]">来源类型</dt>
                  <dd className="mt-1 flex items-center gap-2 font-medium"><FileText className="size-4 text-[#324b6b]" />{selected.source.type}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-[#778399]">来源标识</dt>
                  <dd className="mt-1 break-all font-mono text-xs">{selected.source.id}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-[#778399]">版本</dt>
                  <dd className="mt-1 font-medium">{selected.source.version}</dd>
                </div>
                <div>
                  <dt className="text-xs font-semibold text-[#778399]">精确定位</dt>
                  <dd className="mt-1 rounded-lg bg-[#f1f4f1] p-3 font-mono text-xs">{selected.source.locator}</dd>
                </div>
              </dl>

              {selected.source.href ? (
                <a className="inline-flex items-center gap-2 text-sm font-semibold text-[#243f63] hover:underline" href={selected.source.href} target="_blank" rel="noreferrer">
                  打开授权来源<ExternalLink className="size-4" />
                </a>
              ) : (
                <p className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-5 text-amber-900">
                  当前来源未提供可直接打开的链接；请使用上方版本和定位信息核对。
                </p>
              )}
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
