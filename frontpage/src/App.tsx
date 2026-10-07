import { useEffect, useMemo, useRef, useState } from "react";
import {
  motion,
  MotionConfig,
  useInView,
  useReducedMotion,
  useScroll,
  useTransform,
} from "motion/react";
import { Action, Arrow, Reveal, Rule, SectionLabel } from "./components";
import {
  ConversationExample,
  NormalExample,
  RecollectionExample,
  ThoughtExample,
} from "./Examples";
import { MotionContext, snappy, usePageMotion } from "./motion";

function Hero() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref);
  const { still, visible } = usePageMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const leftY = useTransform(scrollYProgress, [0, 1], [0, -60]);
  const rightY = useTransform(scrollYProgress, [0, 1], [0, -90]);
  const entry = (delay: number) => ({
    initial: false as const,
    animate: still ? { opacity: [0.8, 1] } : { opacity: [0.5, 1], y: [16, 0] },
    transition: still
      ? { duration: 0.15 }
      : { ...snappy, visualDuration: 0.45, delay },
  });

  return (
    <section
      className={`hero ${inView && !still && visible ? "ambient-running" : ""}`}
      ref={ref}
      aria-labelledby="hero-heading"
    >
      <div className="hero-haze haze-one" aria-hidden="true" />
      <div className="hero-haze haze-two" aria-hidden="true" />
      <div className="hero-content">
        <motion.p className="eyebrow" {...entry(0.04)}>
          <span className="small-dot" />a little room for your thoughts.
        </motion.p>
        <h1 id="hero-heading" aria-label="note taking at its purest form.">
          {["note taking at", "its purest form."].map((line, index) => (
            <span className="headline-mask" key={line} aria-hidden="true">
              <motion.span
                className={index === 1 ? "italic" : ""}
                initial={false}
                animate={
                  still
                    ? { opacity: [0.8, 1] }
                    : { y: ["100%", "0%"], opacity: [0.5, 1] }
                }
                transition={
                  still
                    ? { duration: 0.15 }
                    : {
                        ...snappy,
                        visualDuration: 0.5,
                        delay: 0.08 + index * 0.08,
                      }
                }
              >
                {line}
              </motion.span>
            </span>
          ))}
        </h1>
        <motion.p className="hero-description" {...entry(0.24)}>
          a home for the thoughts that arrive unfinished.
          <br className="desktop-break" /> let them out. find their meaning.
          come back to them.
        </motion.p>
        <motion.div className="hero-action" {...entry(0.32)}>
          <Action>follow a thought</Action>
        </motion.div>
      </div>
      <motion.div
        className="hero-fragment fragment-left"
        style={still ? undefined : { y: leftY }}
        {...entry(0.16)}
        aria-hidden="true"
      >
        <span className="fragment-mark">a passing thought.</span>
        <p>
          books, coffee,
          <br />
          people staying a while.
        </p>
        <span className="fragment-underline" />
      </motion.div>
      <motion.div
        className="hero-fragment fragment-right"
        style={still ? undefined : { y: rightY }}
        {...entry(0.24)}
        aria-hidden="true"
      >
        <span className="fragment-mark">a small beginning.</span>
        <p>
          one table
          <br />
          on sundays.
        </p>
        <span className="fragment-underline" />
      </motion.div>
      <motion.div className="hero-foot" {...entry(0.32)}>
        <span>
          from a passing thought.
          <br />
          to something worth keeping.
        </span>
        <a className="scroll-link" href="#idea">
          <span>take your time.</span>
          <Arrow direction="down" />
        </a>
        <span className="hero-foot-right">
          vanille is taking shape.
          <br />a glimpse of what is to come.
        </span>
      </motion.div>
    </section>
  );
}

function Navigation({
  paused,
  onToggle,
}: {
  paused: boolean;
  onToggle: () => void;
}) {
  const { still } = usePageMotion();
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menuOpen]);
  return (
    <motion.header
      className="site-header"
      initial={false}
      animate={
        still ? { opacity: [0.8, 1] } : { opacity: [0.5, 1], y: [-8, 0] }
      }
      transition={{ ...snappy, visualDuration: 0.45 }}
    >
      <a href="#top" className="wordmark" aria-label="vanille home">
        vanille.
      </a>
      <nav
        id="page-navigation"
        className={`navigation ${menuOpen ? "navigation-open" : ""}`}
        aria-label="main navigation"
      >
        {[
          { href: "#idea", text: "the idea." },
          { href: "#modes", text: "two ways." },
          { href: "#recollection", text: "recollection." },
        ].map((item) => (
          <a
            className="text-link"
            href={item.href}
            key={item.href}
            onClick={() => setMenuOpen(false)}
          >
            {item.text}
          </a>
        ))}
      </nav>
      <div className="header-actions">
        <button
          className="motion-control"
          type="button"
          onClick={onToggle}
          aria-label={paused ? "resume page motion" : "pause page motion"}
          aria-pressed={paused}
          title={paused ? "resume motion" : "pause motion"}
        >
          {paused ? (
            <svg
              width="16"
              height="16"
              viewBox="0 0 20 20"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="m7 4 9 6-9 6V4Z"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            <svg
              width="16"
              height="16"
              viewBox="0 0 20 20"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M7 5v10m6-10v10"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          )}
        </button>
        <a className="header-cta text-link" href="#thought">
          explore vanille
          <Arrow />
        </a>
        <button
          className="menu-toggle"
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
          aria-controls="page-navigation"
        >
          {menuOpen ? "close." : "menu."}
        </button>
      </div>
    </motion.header>
  );
}

export default function App() {
  const reduced = useReducedMotion() ?? false;
  const [paused, setPaused] = useState(false);
  const [visible, setVisible] = useState(!document.hidden);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  const settings = useMemo(
    () => ({ paused, reduced, visible }),
    [paused, reduced, visible],
  );

  return (
    <MotionContext.Provider value={settings}>
      <MotionConfig reducedMotion={reduced || paused ? "always" : "never"}>
        <div
          id="top"
          className={`page ${paused || reduced ? "motion-still" : ""}`}
        >
          <a className="skip-link" href="#main">
            skip to content.
          </a>
          <Navigation
            paused={paused}
            onToggle={() => setPaused((value) => !value)}
          />
          <main id="main">
            <Hero />
            <section
              id="idea"
              className="idea-section section-shell"
              aria-labelledby="idea-heading"
            >
              <Rule />
              <div className="idea-layout">
                <SectionLabel number="01">before the words.</SectionLabel>
                <div className="idea-copy">
                  <Reveal>
                    <h2 id="idea-heading">
                      you do not need to
                      <br />
                      make sense. <em>yet.</em>
                    </h2>
                  </Reveal>
                  <Reveal delay={0.08}>
                    <p>
                      a thought rarely arrives neatly written. it comes in
                      pieces. a feeling, a half sentence, a connection you
                      cannot quite explain.
                    </p>
                  </Reveal>
                  <Reveal delay={0.16}>
                    <p>
                      vanille begins there. a place to speak or write freely,
                      and let the shape of an idea emerge.
                    </p>
                  </Reveal>
                </div>
                <Reveal className="idea-margin" delay={0.16}>
                  <span className="margin-symbol" aria-hidden="true">
                    ✳
                  </span>
                  <p>
                    the thought comes first.
                    <br />
                    the structure follows.
                  </p>
                </Reveal>
              </div>
            </section>
            <section
              id="thought"
              className="thought-section section-shell"
              aria-labelledby="thought-heading"
            >
              <div className="section-heading-row">
                <div>
                  <SectionLabel number="02">
                    a thought takes shape.
                  </SectionLabel>
                  <Reveal>
                    <h2 id="thought-heading">
                      a little messy.
                      <br />
                      <em>a little more meaningful.</em>
                    </h2>
                  </Reveal>
                </div>
                <Reveal className="section-description" delay={0.08}>
                  <p>
                    from your original words to the ideas inside them.
                    connected, with the context still close.
                  </p>
                </Reveal>
              </div>
              <Reveal className="thought-stage-wrap">
                <ThoughtExample />
              </Reveal>
              <Reveal className="example-disclaimer">
                <span>an illustrative sequence.</span>
                <span>
                  planned capabilities, shown through one small thought.
                </span>
              </Reveal>
            </section>
            <section
              id="modes"
              className="modes-section section-shell"
              aria-labelledby="modes-heading"
            >
              <Rule />
              <div className="section-heading-row">
                <div>
                  <SectionLabel number="03">two ways to think.</SectionLabel>
                  <Reveal>
                    <h2 id="modes-heading">
                      let it out.
                      <br />
                      <em>or talk it through.</em>
                    </h2>
                  </Reveal>
                </div>
                <Reveal className="section-description" delay={0.08}>
                  <p>
                    some thoughts just need a place to land. others grow when
                    you give them a little company.
                  </p>
                </Reveal>
              </div>
              <div className="mode-columns">
                <article className="mode-column">
                  <Reveal>
                    <NormalExample />
                  </Reveal>
                  <Reveal className="mode-copy" delay={0.08}>
                    <span className="tiny-label">normal.</span>
                    <h3>room to ramble.</h3>
                    <p>
                      speak or write whatever is on your mind. vanille is being
                      designed to organize the meaning, and surface related
                      ideas when you ask.
                    </p>
                  </Reveal>
                </article>
                <article className="mode-column">
                  <Reveal delay={0.08}>
                    <ConversationExample />
                  </Reveal>
                  <Reveal className="mode-copy" delay={0.16}>
                    <span className="tiny-label">conversational.</span>
                    <h3>a thought, in good company.</h3>
                    <p>
                      explore an idea in conversation. elaborate, challenge,
                      find another angle. with spoken recollection and a record
                      to return to.
                    </p>
                  </Reveal>
                </article>
              </div>
            </section>
            <section
              id="recollection"
              className="recollection-section"
              aria-labelledby="recollection-heading"
            >
              <div className="section-shell">
                <Rule />
                <SectionLabel number="04">
                  the thought stays with you.
                </SectionLabel>
                <Reveal className="recollection-heading">
                  <h2 id="recollection-heading">
                    come back to the idea.
                    <br />
                    <em>and everything around it.</em>
                  </h2>
                  <p>
                    a thought becomes more useful when you can find it again.
                    <br className="desktop-break" /> with its connections, its
                    context, and the words that started it.
                  </p>
                </Reveal>
                <RecollectionExample />
                <Reveal className="recollection-caption">
                  <span className="small-dot" />
                  your words remain part of the story.
                </Reveal>
              </div>
            </section>
            <section
              className="closing-section section-shell"
              aria-labelledby="closing-heading"
            >
              <Rule />
              <Reveal>
                <p className="eyebrow">
                  a thought does not have to be finished to be worth keeping.
                </p>
              </Reveal>
              <Reveal>
                <h2 id="closing-heading">
                  leave a little room
                  <br />
                  <em>for what is on your mind.</em>
                </h2>
              </Reveal>
              <Reveal className="closing-action" delay={0.08}>
                <Action>follow a thought</Action>
                <p>vanille is taking shape. this is a first glimpse.</p>
              </Reveal>
            </section>
          </main>
          <footer className="footer section-shell">
            <Rule />
            <div className="footer-top">
              <Reveal>
                <a href="#top" className="text-link">
                  back to the beginning.
                  <Arrow direction="up" />
                </a>
              </Reveal>
              <Reveal delay={0.08}>
                <span>note taking at its purest form.</span>
              </Reveal>
            </div>
            <Reveal className="footer-wordmark">
              <a href="#top" aria-label="vanille, back to top">
                vanille.
              </a>
            </Reveal>
            <div className="footer-bottom">
              <Reveal>
                <span>a place for unfinished thoughts.</span>
              </Reveal>
              <Reveal delay={0.08}>
                <a href="#thought" className="text-link">
                  a glimpse of vanille.
                  <Arrow />
                </a>
              </Reveal>
            </div>
          </footer>
        </div>
      </MotionConfig>
    </MotionContext.Provider>
  );
}
