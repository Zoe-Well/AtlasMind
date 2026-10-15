import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ChatShell } from "@/components/chat/chat-shell";
import { AppShell } from "@/components/layout/app-shell";
import { QueryProvider } from "@/components/providers/query-provider";
import type { AgentRun } from "@/lib/api/client";

const {replace}=vi.hoisted(()=>({replace:vi.fn()}));
vi.mock("next/navigation",()=>({useRouter:()=>({replace}),usePathname:()=>"/chat"}));
const server=setupServer();
const cid="00000000-0000-4000-8000-000000000101";
const conversation={id:cid,title:"退款规则",createdAt:"2026-10-13T00:00:00Z",updatedAt:"2026-10-13T00:00:00Z"};
function turn(ordinal:number,query:string|null,answer:string):AgentRun {
  return {
    id:`00000000-0000-4000-8000-${String(ordinal).padStart(12,"0")}`,conversationId:cid,
    correlationId:cid,turnIndex:ordinal,query,state:"COMPLETED",createdAt:conversation.createdAt,
    answer:{text:answer,confidence:"HIGH",evidenceStatus:"SUFFICIENT",citations:[{
      id:`citation-${ordinal}`,claimLocator:answer,supportStatus:"SUPPORTED",
      source:{type:"DOCUMENT",id:cid,version:"v1",title:`来源 ${ordinal}`,locator:`第 ${ordinal} 段`},
    }]},links:{self:`/v1/agent-runs/${ordinal}`},
  };
}
function history(items:AgentRun[]) {
  server.use(http.get(`/api/platform/conversations/${cid}`,()=>HttpResponse.json({conversation,items,nextBefore:null})));
}
beforeAll(()=>server.listen({onUnhandledRequest:"error"}));
afterEach(()=>{server.resetHandlers();replace.mockReset()});
afterAll(()=>server.close());

describe("persisted conversations",()=>{
  it("restores every question and answer after remount and appends without replacing old turns",async()=>{
    const items=[turn(1,"第一问","第一答"),turn(2,"第二问","第二答")];
    history(items);
    server.use(http.post("/api/agent-runs",async({request})=>{
      expect(await request.json()).toEqual({query:"第三问",mode:"AUTO",conversationId:cid});
      const next=turn(3,"第三问","第三答");items.push(next);
      return HttpResponse.json(next,{status:202});
    }));
    const view=render(<QueryProvider><ChatShell mode="local" conversationId={cid}/></QueryProvider>);
    expect(await screen.findByText("第一问")).toBeVisible();
    expect(screen.getByText("第二答")).toBeVisible();
    const user=userEvent.setup();
    await user.type(screen.getByLabelText("向企业知识库提问"),"第三问");
    await user.click(screen.getByRole("button",{name:"发送问题"}));
    expect(await screen.findByText("第三答")).toBeVisible();
    expect(screen.getByText("第一答")).toBeVisible();
    expect(screen.getAllByRole("link",{name:"查看本轮运行详情"})).toHaveLength(3);
    view.unmount();
    render(<QueryProvider><ChatShell mode="local" conversationId={cid}/></QueryProvider>);
    expect(await screen.findByText("第三答")).toBeVisible();
    expect(screen.getByText("第一问")).toBeVisible();
    expect(screen.getAllByRole("region").map(region=>region.getAttribute("aria-label")))
      .toEqual(["第 1 轮问答","第 2 轮问答","第 3 轮问答"]);
  });

  it("selects evidence for the corresponding turn",async()=>{
    history([turn(1,"第一问","第一答"),turn(2,"第二问","第二答")]);
    render(<QueryProvider><ChatShell mode="local" conversationId={cid}/></QueryProvider>);
    expect(await screen.findByText("来源 2")).toBeVisible();
    await userEvent.click(within(screen.getByRole("region",{name:"第 1 轮问答"})).getByRole("button",{name:"查看本轮来源（1）"}));
    expect(screen.getByText("来源 1")).toBeVisible();
    expect(screen.queryByText("来源 2")).not.toBeInTheDocument();
  });

  it("marks missing legacy questions and preserves their saved answers",async()=>{
    history([turn(1,null,"历史回答")]);
    render(<QueryProvider><ChatShell mode="local" conversationId={cid}/></QueryProvider>);
    expect(await screen.findByText("历史回答")).toBeVisible();
    expect(screen.getByText("原问题未保存，无法恢复；以下为当时保存的回答。")).toBeVisible();
  });

  it("loads earlier turns in chronological order",async()=>{
    server.use(http.get(`/api/platform/conversations/${cid}`,({request})=>{
      const earlier=new URL(request.url).searchParams.get("before")==="3";
      return HttpResponse.json({conversation,items:earlier?[turn(1,"第一问","第一答"),turn(2,"第二问","第二答")]:[turn(3,"第三问","第三答")],nextBefore:earlier?null:3});
    }));
    render(<QueryProvider><ChatShell mode="local" conversationId={cid}/></QueryProvider>);
    await userEvent.click(await screen.findByRole("button",{name:"加载更早的问答"}));
    expect(await screen.findByText("第一答")).toBeVisible();
    expect(screen.getAllByRole("region").map(region=>region.getAttribute("aria-label")))
      .toEqual(["第 1 轮问答","第 2 轮问答","第 3 轮问答"]);
  });

  it("starts a separate conversation and updates the restorable URL",async()=>{
    server.use(http.post("/api/agent-runs",async({request})=>{
      expect(await request.json()).toEqual({query:"新问题",mode:"AUTO"});
      return HttpResponse.json(turn(1,"新问题","新回答"),{status:202});
    }));
    render(<QueryProvider><ChatShell mode="local"/></QueryProvider>);
    await userEvent.type(screen.getByLabelText("向企业知识库提问"),"新问题");
    await userEvent.click(screen.getByRole("button",{name:"发送问题"}));
    await waitFor(()=>expect(replace).toHaveBeenCalledWith(`/chat/${cid}`,{scroll:false}));
  });

  it("disables submitting to an inaccessible conversation",async()=>{
    server.use(http.get(`/api/platform/conversations/${cid}`,()=>HttpResponse.json({}, {status:404})));
    render(<QueryProvider><ChatShell mode="local" conversationId={cid}/></QueryProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("对象不存在或当前身份不可见");
    expect(screen.getByRole("button",{name:"发送问题"})).toBeDisabled();
  });

  it("routes history to conversations while retaining the run center",async()=>{
    server.use(http.get("/api/platform/conversations",()=>HttpResponse.json({items:[conversation],nextOffset:null})));
    render(<QueryProvider><AppShell session={{displayName:"Tester",mode:"local",authenticated:true}}><div/></AppShell></QueryProvider>);
    expect(await screen.findByRole("link",{name:/退款规则/})).toHaveAttribute("href",`/chat/${cid}`);
    expect(screen.getByRole("link",{name:"运行中心"})).toHaveAttribute("href","/runs");
    expect(screen.getByRole("link",{name:/新建对话/})).toHaveAttribute("href","/chat");
  });
});
