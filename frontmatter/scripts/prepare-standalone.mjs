import { cpSync } from "node:fs";

// Next.js leaves static assets outside its standalone production bundle.
cpSync("public", ".next/standalone/public", { recursive: true });
cpSync(".next/static", ".next/standalone/.next/static", { recursive: true });
