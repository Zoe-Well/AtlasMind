import { cva,type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
const buttonVariants=cva("inline-flex items-center justify-center gap-2 rounded-[9px] font-semibold transition disabled:pointer-events-none disabled:opacity-45",{variants:{variant:{primary:"border border-[#4d55ca] bg-[#4d55ca] text-white hover:bg-[#4148b4]",secondary:"border border-[#deded9] bg-white text-[#20212a] hover:bg-[#f5f5f2]",ghost:"border border-transparent text-[#656975] hover:bg-[#e9e9e5] hover:text-[#20212a]",danger:"border border-[#e6c5c5] bg-white text-[#9b4040] hover:bg-[#faeaea]",dark:"border border-[#252733] bg-[#252733] text-white hover:bg-[#1e2029]"},size:{md:"h-10 px-4 text-xs",sm:"h-[30px] px-2.5 text-[11px]",icon:"size-9 p-0"}},defaultVariants:{variant:"primary",size:"md"}});
type Props=ButtonHTMLAttributes<HTMLButtonElement>&VariantProps<typeof buttonVariants>;
export function Button({className,variant,size,...props}:Props){return <button className={cn(buttonVariants({variant,size}),className)} {...props}/>;}
