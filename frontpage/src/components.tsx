import type { ReactNode } from "react";
import { motion } from "motion/react";
import { snappy, usePageMotion } from "./motion";

export function Arrow({
  direction = "up",
}: {
  direction?: "up" | "down" | "right";
}) {
  return (
    <svg
      className={`arrow arrow-${direction}`}
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M5 19 19 5M5 5h14v14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const { still } = usePageMotion();
  return (
    <motion.div
      className={className}
      initial={false}
      whileInView={
        still ? { opacity: [0.8, 1] } : { opacity: [0.4, 1], y: [20, 0] }
      }
      viewport={{ once: true, amount: 0.15 }}
      transition={
        still ? { duration: 0.15 } : { ...snappy, visualDuration: 0.55, delay }
      }
    >
      {children}
    </motion.div>
  );
}

export function Rule({ className = "" }: { className?: string }) {
  const { still } = usePageMotion();
  return (
    <motion.div
      className={`rule ${className}`}
      aria-hidden="true"
      initial={false}
      whileInView={
        still ? { opacity: [0.5, 1] } : { scaleX: [0.2, 1], opacity: [0.5, 1] }
      }
      viewport={{ once: true }}
      transition={
        still ? { duration: 0.15 } : { ...snappy, visualDuration: 0.6 }
      }
    />
  );
}

export function SectionLabel({
  number,
  children,
}: {
  number: string;
  children: ReactNode;
}) {
  return (
    <Reveal className="section-label">
      <span>{number}</span>
      <span>{children}</span>
    </Reveal>
  );
}

export function Action({
  children,
  href = "#thought",
}: {
  children: ReactNode;
  href?: string;
}) {
  return (
    <a className="action" href={href}>
      <span>{children}</span>
      <span className="action-icon">
        <Arrow />
      </span>
    </a>
  );
}
