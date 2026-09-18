import { cn } from "@/lib/utils";

interface ErrorBannerProps {
  message: string | null;
  className?: string;
}

export function ErrorBanner({ message, className }: ErrorBannerProps) {
  if (!message) return null;
  return (
    <p
      role="alert"
      className={cn(
        "font-body-sm text-body-sm text-error bg-error-container/40 rounded-lg px-3 py-2",
        className
      )}
    >
      {message}
    </p>
  );
}
