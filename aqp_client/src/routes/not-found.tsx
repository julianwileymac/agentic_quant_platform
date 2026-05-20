import { ArrowLeft, Compass } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function NotFoundRoute() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
      <Compass className="h-12 w-12 text-[var(--text-secondary)]" />
      <div>
        <h1 className="text-2xl font-semibold">Route not found</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          The path doesn&apos;t match any registered AQP surface.
        </p>
      </div>
      <Button asChild variant="outline">
        <Link to="/">
          <ArrowLeft className="h-4 w-4" /> Back to Dashboard
        </Link>
      </Button>
    </div>
  );
}
