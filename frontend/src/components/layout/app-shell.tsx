"use client";

import { Activity, Beaker, ChevronDown, Database, GitFork, LockKeyhole, LogOut, MessageSquareText, Network, Plus, ShieldCheck, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { PublicSession } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

const primaryNavigation = [
  { href: "/chat", label: "智能问答", icon: MessageSquareText },
  { href: "/knowledge", label: "数据接入", icon: Database },
  { href: "/graph", label: "知识图谱", icon: Network },
  { href: "/rag", label: "RAG 策略", icon: SlidersHorizontal, badge: "占位" },
];
const operationNavigation = [
  { href: "/runs", label: "运行中心", icon: Activity },
  { href: "/approvals", label: "审批中心", icon: ShieldCheck },
  { href: "/evaluations", label: "质量评估", icon: Beaker },
  { href: "/governance", label: "权限与审计", icon: LockKeyhole },
];

function NavGroup({ items }: { items: typeof primaryNavigation }) {
  const pathname = usePathname();
  return <nav className="grid gap-1" aria-label="主要功能">{items.map((item) => {
    const active = pathname === item.href || (item.href !== "/chat" && pathname.startsWith(`${item.href}/`));
    return <Link key={item.href} href={item.href} className={cn("flex min-h-10 items-center gap-3 rounded-[10px] px-3 text-[13px] font-medium text-[#555964] transition-colors hover:bg-[#e7e7e2] hover:text-[#20212a]", active && "bg-[#e1e1dc] font-semibold text-[#20212a]")}>
      <item.icon className={cn("size-[17px] stroke-[1.8]", active && "text-[#4d55ca]")} />
      <span>{item.label}</span>
      {item.badge ? <span className="ml-auto rounded-full bg-[#e3e3df] px-2 py-0.5 text-[10px] text-[#777b84]">{item.badge}</span> : null}
    </Link>;
  })}</nav>;
}

export function AppShell({ session, children }: { session: PublicSession; children: React.ReactNode }) {
  return <div className="app-frame">
    <aside className="app-sidebar">
      <Link href="/chat" className="flex items-center gap-3 px-2" aria-label="AtlasMind 首页">
        <span className="grid size-8 place-items-center rounded-[9px] bg-[#4d55ca] text-white"><GitFork className="size-[17px] rotate-90" /></span>
        <span className="text-[15px] font-bold tracking-[-0.02em] text-[#20212a]">AtlasMind</span>
      </Link>
      <Link href="/chat" className="mt-6 flex min-h-10 items-center gap-3 rounded-[10px] bg-[#252733] px-3 text-[13px] font-semibold text-white hover:bg-[#1e2029]">
        <Plus className="size-4" />新建对话<span className="ml-auto font-mono text-[10px] text-[#aeb1bd]">⌘ K</span>
      </Link>
      <p className="sidebar-label">工作台</p><NavGroup items={primaryNavigation} />
      <div className="mx-2 mt-[18px] h-px bg-[#dcdcd7]" />
      <p className="sidebar-label">运营与治理</p><NavGroup items={operationNavigation} />
      <p className="sidebar-label history-heading">历史对话</p>
      <div className="min-h-0 overflow-hidden">
        <Link href="/chat" className="block truncate rounded-[9px] bg-[#e5e5e0] px-3 py-2.5 text-xs text-[#20212a]">企业退款政策与申请流程</Link>
        <p className="mt-1 px-3 py-2 text-[11px] leading-5 text-[#858995]">历史列表接口待接入</p>
      </div>
      <div className="mt-auto flex items-center gap-3 rounded-xl bg-[#e8e8e4] p-2.5">
        <span className="grid size-[34px] shrink-0 place-items-center rounded-full bg-[#d8d9f6] text-xs font-bold text-[#4d55ca]">{session.displayName.slice(0, 1).toUpperCase()}</span>
        <div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold text-[#20212a]">{session.displayName}</p><p className="mt-0.5 truncate text-[10px] text-[#858995]">{session.mode === "local" ? "本地真实数据" : "企业成员"}</p></div>
        <ChevronDown className="size-3.5 text-[#858995]" />
      </div>
      <form action="/api/auth/logout" method="post" className="mt-2"><button type="submit" className="flex w-full items-center justify-center gap-2 rounded-lg py-1.5 text-[10px] text-[#858995] hover:bg-[#e5e5e0] hover:text-[#555964]"><LogOut className="size-3" />退出登录</button></form>
    </aside>
    <main className="app-main">{children}</main>
  </div>;
}
