import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useInView } from "motion/react";

export const snappy = {
  type: "spring",
  stiffness: 400,
  damping: 30,
  mass: 1,
} as const;
export const smooth = {
  type: "spring",
  stiffness: 200,
  damping: 24,
  mass: 1,
} as const;
export const MotionContext = createContext({
  paused: false,
  reduced: false,
  visible: true,
});

export function usePageMotion() {
  const settings = useContext(MotionContext);
  return { ...settings, still: settings.paused || settings.reduced };
}

// Illustrations play once, suspend off screen, and leave a readable final state.
export function useExample(finalStep: number, readingHold = 1800) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.3 });
  const { paused, reduced, visible } = usePageMotion();
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!inView || paused || reduced || !visible || step >= finalStep) return;
    const timer = window.setTimeout(
      () => setStep((current) => current + 1),
      readingHold,
    );
    return () => window.clearTimeout(timer);
  }, [inView, paused, reduced, visible, step, finalStep, readingHold]);

  return {
    ref,
    step: reduced ? finalStep : step,
    running: inView && !paused && !reduced && visible && step < finalStep,
    replay: () => setStep(0),
  };
}
