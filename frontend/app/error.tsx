"use client";

import { useEffect } from "react";
import { Icon } from "@/components/icons";
import { Button, EmptyState } from "@/components/ui";

/** Route error boundary: a render error shows this inside the app frame instead of a blank
 *  page (e.g. an eval report written by a newer version of the eval script). */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="py-10">
      <EmptyState
        title="This page hit an error"
        icon="alert"
        action={
          <Button variant="primary" onClick={reset}>
            <Icon name="refresh" className="size-3.5" />
            Try again
          </Button>
        }
      >
        Something on this page failed to render. Other pages still work.
        {error.digest && <span className="mt-1 block font-mono text-caption">{error.digest}</span>}
      </EmptyState>
    </div>
  );
}
