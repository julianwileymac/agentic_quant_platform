// Type shim so TypeScript accepts the side-effect CSS import shipped with
// the `xterm` package.  Next.js handles CSS at build time via PostCSS; this
// shim is only here to satisfy `tsc --noEmit` (the strict check Next runs
// during `next build`).
declare module 'xterm/css/xterm.css'
