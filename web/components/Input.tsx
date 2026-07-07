// Shared Input primitive — D-02 token layer + D-03 focus-visible floor.
import type { InputHTMLAttributes } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  "data-testid"?: string;
}

const BASE_CLASSES =
  "w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm outline-none " +
  "focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-neutral-950 " +
  "dark:border-neutral-700 dark:bg-neutral-900";

export default function Input({ className, ...props }: InputProps) {
  const classes = [BASE_CLASSES, className].filter(Boolean).join(" ");

  return <input className={classes} {...props} />;
}
