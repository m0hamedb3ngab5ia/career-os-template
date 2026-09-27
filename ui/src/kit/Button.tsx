import { Loader2 } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import styles from "./controls.module.css";

export type ButtonVariant = "primary" | "secondary" | "destructive" | "destructive-filled";

interface ButtonProps extends Omit<ComponentProps<"button">, "children"> {
  variant?: ButtonVariant;
  size?: "regular" | "small";
  /** The request has started: the button disables and shows `pendingLabel` ("Saving…") with a spinner. */
  pending?: boolean;
  pendingLabel?: string;
  icon?: ReactNode;
  children: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "regular",
  pending = false,
  pendingLabel,
  icon,
  children,
  type = "button",
  disabled,
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      className={className ? `${styles.button} ${className}` : styles.button}
      data-variant={variant}
      data-size={size}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
    >
      {pending ? <Loader2 size={14} className={styles.spinner} aria-hidden="true" /> : icon}
      {pending && pendingLabel ? pendingLabel : children}
    </button>
  );
}
