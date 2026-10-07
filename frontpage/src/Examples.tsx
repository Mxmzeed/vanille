import { motion } from "motion/react";
import { Arrow, Reveal } from "./components";
import { smooth, useExample, usePageMotion } from "./motion";

const concepts = [
  {
    number: "01",
    title: "a neighborhood reading room.",
    source: "a little reading room in the neighborhood.",
    tag: "a place",
  },
  {
    number: "02",
    title: "a reason to stay a while.",
    source: "books, coffee, people staying a while.",
    tag: "a feeling",
  },
  {
    number: "03",
    title: "begin with something small.",
    source: "one table on sundays.",
    tag: "a beginning",
  },
];

export function ThoughtExample() {
  const { ref, step, running, replay } = useExample(3, 1900);
  const { still, reduced, paused } = usePageMotion();
  const current = Math.min(step, 2);
  return (
    <div
      ref={ref}
      className={`thought-stage ${running ? "is-running" : ""}`}
      data-step={step}
    >
      <div className="stage-topline">
        <span className="example-label">
          <span className="small-dot" />
          an example thought.
        </span>
        <span className="stage-note">a preview of what we are building.</span>
      </div>
      <div className="thought-composition">
        <motion.div
          className="source-paper"
          initial={false}
          animate={
            still
              ? { opacity: 1 }
              : { rotate: step > 0 ? -1 : -3, y: step > 0 ? 0 : 8 }
          }
          transition={smooth}
        >
          <div className="paper-heading">
            <span>your words.</span>
            <span className="paper-corner" aria-hidden="true">
              ↙
            </span>
          </div>
          <p className="source-thought">
            i keep thinking about{" "}
            <span className={`ink-highlight ${step >= 1 ? "highlighted" : ""}`}>
              a little reading room in the neighborhood.
            </span>{" "}
            <span className={`ink-highlight ${step >= 2 ? "highlighted" : ""}`}>
              books, coffee, people staying a while.
            </span>{" "}
            maybe it starts with{" "}
            <span className={`ink-highlight ${step >= 3 ? "highlighted" : ""}`}>
              one table on sundays.
            </span>
          </p>
          <div className="paper-foot">
            <span className="source-stamp">the original thought</span>
            <span>still yours.</span>
          </div>
        </motion.div>
        <div className="thought-thread" aria-hidden="true">
          <svg viewBox="0 0 180 340" fill="none" preserveAspectRatio="none">
            {[55, 170, 285].map((end, index) => (
              <motion.path
                key={end}
                d={`M0 170 C90 170 70 ${end} 180 ${end}`}
                stroke="currentColor"
                strokeWidth="1"
                initial={false}
                animate={{
                  opacity: step > index ? 0.5 : 0.12,
                  pathLength: reduced ? 1 : step > index ? 1 : 0,
                }}
                transition={
                  still
                    ? { duration: 0 }
                    : {
                        duration: 0.65,
                        delay: index * 0.1,
                        ease: [0.16, 1, 0.3, 1],
                      }
                }
              />
            ))}
          </svg>
          <motion.span
            className="thread-knot"
            initial={false}
            animate={
              still
                ? { opacity: 1 }
                : { scale: step > 0 ? 1 : 0.65, rotate: step > 0 ? 90 : 0 }
            }
            transition={smooth}
          >
            ✳
          </motion.span>
        </div>
        <div
          className="concept-sheets"
          aria-label="related concepts from the example thought"
        >
          {concepts.map((concept, index) => (
            <motion.div
              className="concept-sheet"
              key={concept.number}
              initial={false}
              animate={
                still
                  ? { opacity: reduced || step > index ? 1 : 0.35 }
                  : {
                      opacity: step > index ? 1 : 0.35,
                      x: step > index ? 0 : 28 + index * 8,
                      y: step > index ? 0 : (index - 1) * 12,
                      rotate: step > index ? 0 : (index - 1) * 3,
                    }
              }
              transition={
                still ? { duration: 0.15 } : { ...smooth, delay: index * 0.1 }
              }
            >
              <div className="concept-index">{concept.number}</div>
              <div className="concept-content">
                <span className="concept-tag">{concept.tag}</span>
                <h3>{concept.title}</h3>
                <p>
                  <span>from your words.</span> {concept.source}
                </p>
              </div>
              <span className="concept-cross" aria-hidden="true">
                +
              </span>
            </motion.div>
          ))}
        </div>
      </div>
      <div className="stage-bottomline">
        <ol className="example-steps" aria-label="example progression">
          {["let it out.", "find the threads.", "keep the meaning."].map(
            (label, index) => (
              <li
                key={label}
                className={index <= current ? "step-active" : ""}
                aria-current={index === current ? "step" : undefined}
              >
                <span className="step-number">0{index + 1}</span>
                <span>{label}</span>
                <span className="step-line" aria-hidden="true" />
              </li>
            ),
          )}
        </ol>
        <button
          type="button"
          className="replay-button"
          onClick={replay}
          disabled={reduced || paused}
          aria-label="replay the thought example"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 20 20"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M3 9a7 7 0 1 1 1 5M3 4v5h5"
              stroke="currentColor"
              strokeWidth="1.3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span>replay</span>
        </button>
      </div>
      <p className="sr-only">
        this illustrative example shows a rough thought about a reading room
        becoming three related concepts. the original words remain alongside the
        interpretation. the sequence does not represent live processing.
      </p>
    </div>
  );
}

function Waveform({ running }: { running: boolean }) {
  const { still } = usePageMotion();
  return (
    <div
      className={`waveform ${running && !still ? "waveform-running" : ""}`}
      aria-hidden="true"
    >
      {Array.from({ length: 35 }, (_, index) => (
        <span
          key={index}
          style={{
            height: `${8 + Math.sin(index * 1.8) ** 2 * 25 + Math.sin(index * 0.35) ** 2 * 14}px`,
            animationDelay: `${index * -0.065}s`,
          }}
        />
      ))}
    </div>
  );
}

export function NormalExample() {
  const { ref, step, running } = useExample(2, 2200);
  const { still } = usePageMotion();
  return (
    <div ref={ref} className="mode-example normal-example">
      <div className="mode-example-top">
        <span>normal mode.</span>
        <span>example</span>
      </div>
      <div className="capture-visual">
        <Waveform running={running} />
        <span className="capture-caption">a thought, as it comes.</span>
      </div>
      <motion.div
        className="capture-passage"
        initial={false}
        animate={
          still
            ? { opacity: 1 }
            : { opacity: step > 0 ? 1 : 0.6, y: step > 0 ? 0 : 12 }
        }
        transition={smooth}
      >
        <span className="tiny-label">your words.</span>
        <p>maybe it starts with one table on sundays.</p>
      </motion.div>
      <motion.div
        className="surfaced-thought"
        initial={false}
        animate={
          still
            ? { opacity: 1 }
            : { opacity: step > 1 ? 1 : 0.4, y: step > 1 ? 0 : 16 }
        }
        transition={smooth}
      >
        <span className="surfaced-icon" aria-hidden="true">
          <Arrow direction="right" />
        </span>
        <div>
          <span className="tiny-label">a related thought.</span>
          <p>begin with something small.</p>
        </div>
      </motion.div>
    </div>
  );
}

export function ConversationExample() {
  const { ref, step } = useExample(3, 2200);
  const { still } = usePageMotion();
  const messages = [
    {
      from: "you.",
      message:
        "i think it is less about the books. more about having a place to be.",
    },
    {
      from: "vanille.",
      message: "what would make someone feel they belong there.",
    },
    { from: "you.", message: "not having to buy something to stay." },
  ];
  return (
    <div ref={ref} className="mode-example conversation-example">
      <div className="mode-example-top">
        <span>conversational mode.</span>
        <span>example</span>
      </div>
      <div className="conversation-transcript">
        {messages.map((message, index) => (
          <motion.div
            key={message.message}
            className={`transcript-message ${index === 1 ? "vanille-message" : ""}`}
            initial={false}
            animate={
              still
                ? { opacity: 1 }
                : {
                    opacity: step >= index ? 1 : 0.25,
                    y: step >= index ? 0 : 10,
                  }
            }
            transition={smooth}
          >
            <span>{message.from}</span>
            <p>{message.message}</p>
          </motion.div>
        ))}
      </div>
      <motion.div
        className="spoken-context"
        initial={false}
        animate={{ opacity: step >= 3 || still ? 1 : 0.3 }}
        transition={{ duration: 0.4 }}
      >
        <svg
          width="17"
          height="17"
          viewBox="0 0 20 20"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="m3 8 3 0 4-4v12l-4-4H3V8Zm10-1c2 2 2 4 0 6m3-9c4 4 4 8 0 12"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span>spoken context, with a transcript to keep.</span>
      </motion.div>
    </div>
  );
}

export function RecollectionExample() {
  const { still } = usePageMotion();
  return (
    <div className="recollection-composition">
      <Reveal
        className="recollection-aside recollection-aside-left"
        delay={0.08}
      >
        <span className="tiny-label">a connected idea.</span>
        <h3>start small.</h3>
        <p>one table on sundays.</p>
        <span className="margin-line" aria-hidden="true" />
      </Reveal>
      <Reveal className="recollection-paper">
        <div className="paper-heading">
          <span>recollection.</span>
          <span>example</span>
        </div>
        <span className="tiny-label recollection-category">
          a place. a feeling. a beginning.
        </span>
        <h3>a place to belong.</h3>
        <p className="recollection-body">
          a neighborhood reading room. books and coffee, but also something
          quieter. a place where people can stay a while, without needing a
          reason.
        </p>
        <div className="recollection-source">
          <span className="tiny-label">where the thought began.</span>
          <p>books, coffee, people staying a while.</p>
        </div>
        <motion.div
          className="paper-underlining"
          aria-hidden="true"
          initial={false}
          whileInView={still ? { opacity: 1 } : { scaleX: [0, 1] }}
          viewport={{ once: true }}
          transition={smooth}
        />
      </Reveal>
      <Reveal
        className="recollection-aside recollection-aside-right"
        delay={0.16}
      >
        <span className="tiny-label">a thought, elaborated.</span>
        <h3>stay a while.</h3>
        <p>not having to buy something to stay.</p>
        <span className="margin-line" aria-hidden="true" />
      </Reveal>
    </div>
  );
}
