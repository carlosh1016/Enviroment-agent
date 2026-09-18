import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-space-xs whitespace-nowrap rounded-xl font-label-lg text-label-lg transition-all disabled:opacity-50 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary: "bg-primary text-on-primary shadow-md hover:bg-primary-container",
        secondary:
          "bg-surface-container-lowest text-primary shadow-sm hover:bg-surface-container-low",
        outline:
          "border border-outline-variant text-on-surface hover:bg-surface-container-low",
        ghost: "text-on-surface-variant hover:bg-surface-container-low",
        destructive: "bg-error text-on-error hover:bg-error/90",
      },
      size: {
        default: "px-space-md py-2.5",
        sm: "px-space-sm py-1.5 text-label-md",
        icon: "p-1.5",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
