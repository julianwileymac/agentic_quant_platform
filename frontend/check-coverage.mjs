import fs from "node:fs";

const navHrefs = (await import("./src/components/shell/nav-config.ts")).NAV_ITEMS.map((i) => i.href);
const src = fs.readFileSync("src/routes.tsx", "utf8");

const realStart = src.indexOf("REAL_ROUTES: Record");
const realEnd = src.indexOf("};", realStart);
const realBlock = src.slice(realStart, realEnd);
const real = [...realBlock.matchAll(/"([^"]+)":/g)].map((m) => m[1]);

const dynStart = src.indexOf("DYNAMIC_ROUTES");
const dynEnd = src.indexOf("];", dynStart);
const dynBlock = src.slice(dynStart, dynEnd);
const dyn = [...dynBlock.matchAll(/path:\s*"([^"]+)"/g)].map((m) => "/" + m[1]);

const missing = navHrefs.filter((h) => !real.includes(h) && !dyn.includes(h));
console.log("REAL", real.length, "DYN", dyn.length, "NAV", navHrefs.length);
console.log("MISSING:", missing);
