import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Badge de estado. Colores fijados por spec: processing=amarillo, ready=verde, error=rojo.
 */
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full font-label-sm text-label-sm font-semibold",
  {
    variants: {
      variant: {
        ready: "bg-emerald-50 text-emerald-800",
        processing: "bg-amber-100 text-amber-900",
        error: "bg-red-100 text-red-900",
        neutral: "bg-surface-container-highest text-on-surface-variant",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant, className }))} {...props} />;
}

export { Badge, badgeVariants };
