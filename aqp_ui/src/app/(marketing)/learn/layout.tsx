import type { ReactNode } from "react";

export const dynamic = "force-static";

/**
 * Layout for the /learn hub.
 *
 * The hub index uses a card grid; individual articles use
 * `<LearnArticleLayout>` from src/components/marketing/.
 * This layout just provides the shared section wrapper.
 */
export default function LearnLayout({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: "calc(100vh - 200px)" }}>{children}</div>
  );
}
