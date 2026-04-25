import type { ReactNode } from "react";

import { ShellChrome } from "./ShellChrome";

export default function ShellLayout({ children }: { children: ReactNode }) {
  return <ShellChrome>{children}</ShellChrome>;
}
