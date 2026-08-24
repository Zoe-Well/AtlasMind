import { LockKeyhole } from "lucide-react";
import Link from "next/link";

export default function UnauthorizedPage() {
  return (
    <main className="grid min-h-screen place-items-center px-5">
      <section className="max-w-md rounded-lg border border-[#d8dee8] bg-white p-10 text-center shadow-[0_8px_24px_rgba(23,32,51,0.08)]">
        <span className="mx-auto grid size-14 place-items-center rounded-md bg-[#f3eee6] text-[#8a5314]"><LockKeyhole /></span>
        <h1 className="mt-6 text-2xl font-semibold">此资源当前不可用</h1>
        <p className="mt-3 leading-7 text-[#647087]">资源可能不存在，或当前身份无权查看。为保护企业知识，系统不会披露更多信息。</p>
        <Link href="/chat" className="mt-7 inline-flex rounded-md bg-[#243f63] px-5 py-3 text-sm font-semibold text-white">返回知识问答</Link>
      </section>
    </main>
  );
}
