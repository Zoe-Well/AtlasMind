import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QueryProvider } from "@/components/providers/query-provider";
import { ChatShell } from "./chat-shell";

describe("ChatShell", () => {
  it("labels local persistent data and submits a knowledge question", async () => {
    const user = userEvent.setup();
    const submit = vi.fn().mockResolvedValue(undefined);
    render(
      <QueryProvider>
        <ChatShell mode="local" onSubmit={submit} />
      </QueryProvider>,
    );

    expect(screen.getByText("本地真实数据")).toBeInTheDocument();
    await user.type(screen.getByLabelText("向企业知识库提问"), "退款期限是多少？");
    await user.click(screen.getByRole("button", { name: "发送问题" }));
    expect(submit).toHaveBeenCalledWith("退款期限是多少？");
  });
});
