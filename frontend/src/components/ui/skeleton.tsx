import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("rounded-md bg-muted [animation:skeleton-wait_150ms_step-end,pulse_2s_cubic-bezier(0.4,0,0.6,1)_150ms_infinite]", className)}
      {...props}
    />
  )
}

export { Skeleton }
