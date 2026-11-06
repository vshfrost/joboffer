import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "../lib/cn";
import { Spinner } from "./spinner";

const buttonVariants = cva(
  [
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg",
    "text-nav font-medium transition-colors duration-140",
    "disabled:pointer-events-none disabled:bg-disabled disabled:text-disabled-foreground",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary-hover",
        secondary: "border border-border bg-card text-foreground hover:bg-accent",
        ghost: "text-foreground hover:bg-accent",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
      },
      size: {
        // 40 px; на touch-пристроях цілі від 44 px
        default: "h-10 px-4 pointer-coarse:h-11",
        // компактна друга кнопка на desktop
        sm: "h-8 px-3 pointer-coarse:h-11",
        icon: "size-10 pointer-coarse:size-11",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

type ButtonProps = ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    /** Віддає стилі дочірньому елементу (наприклад, `<Link>`), не додаючи вкладеного `<button>`. */
    asChild?: boolean;
    /** Операція триває: спінер перед текстом, кнопка вимкнена, `aria-busy="true"`. Разом з `asChild` не діє. */
    loading?: boolean;
  };

export function Button({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }: ButtonProps) {
  const classes = cn(buttonVariants({ variant, size }), className);
  if (asChild) {
    return (
      <Slot.Root className={classes} {...props}>
        {children}
      </Slot.Root>
    );
  }
  return (
    <button className={classes} disabled={disabled || loading} aria-busy={loading || undefined} {...props}>
      {loading ? <Spinner /> : null}
      {children}
    </button>
  );
}
