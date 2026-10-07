# frontmatter design.

## status and purpose

This is the design brief for vanille's main application, based on [bootstrap.md](../bootstrap.md). It describes future interface work. The current application remains a bootstrap shell. Writing this document does not implement the modes, recording, conversation, or memory behavior described below.

The person opening vanille has an unfinished thought, often between other tasks. Their immediate goal is to express it before it disappears. Later, they want to recognize its meaning and reconnect it with other ideas. The interface should feel like a quiet place to think, with the warmth of paper and the clarity of a reading tool.

## product world

- Domain vocabulary: fragments, spoken words, threads of thought, source passages, recurring ideas, concept clusters, and recollection.
- Materials: cream paper, white writing sheets, brown ink, graphite, a faint paper edge, and light passing through a translucent margin. All tones come from the four brand colors and their tints.
- Signature: a thought stays readable while its associated concepts appear in the margin. The original words and the system's interpretation remain visibly distinct.
- Patterns to avoid: a dashboard of statistics, a document editor with folders and formatting tools, and a permanent animated graph that competes with reading.

The focal point is the active thought or conversation. Context serves that focal point. The interface should not ask the person to organize information before they can express it.

## shared identity

Use the same palette and type families as the [frontpage brief](../frontpage/design.md). The application uses a quieter scale, less motion, and more stable surfaces.

| existing primitive | value | intended use |
| --- | --- | --- |
| `--color-beige` | `#f3eadc` | continuous page canvas |
| `--color-brown` | `#6b4f3a` | supporting text, selected controls, focus |
| `--color-white` | `#ffffff` | readable sheets and raised context |
| `--color-onyx` | `#242321` | primary text and strongest actions |

Proposed semantic roles should alias these primitives. Use `paper` for the canvas, `ink` for primary text, `secondary-ink` for brown supporting text, and `sheet` for white surfaces. Control fills may mix a small amount of brown into beige. Separators may use brown at low opacity. Do not use those decorative separator colors for meaningful text.

Depth comes primarily from small changes in surface tone. Keep the canvas continuous through navigation and content. Use restrained separators where structure needs an edge, and opaque sheets where text needs a stable background. Blur is reserved for occasional surrounding atmosphere, outside the reading surface.

Interface copy is lowercase, with periods and commas as the preferred punctuation. Keep original user text, quotations, acronyms, and proper nouns intact. Examples of interface labels are `normal`, `conversational`, `listening.`, and `saved.`

## typography and measurements

Proposed families are [IBM Plex Sans](https://github.com/IBM/plex) for controls, transcripts, and body text, and [Newsreader](https://github.com/productiontype/Newsreader) for selected concept titles. These fonts are design choices for later implementation, not currently installed assets. Use a readable system fallback until local font assets are deliberately added.

| role | starting size | treatment |
| --- | --- | --- |
| metadata | 12 to 13 px | restrained weight, readable contrast |
| controls and labels | 14 px | medium weight |
| thought and conversation text | 16 to 18 px | regular weight, 1.55 to 1.7 line height |
| concept heading | 24 px | serif, clear separation from source text |
| view heading | 28 to 32 px | one level above the content |

Use a roughly 1.25 type scale. Establish hierarchy through weight, color, and space as well as size. Keep reading passages around 60 to 70 characters wide. Timers use tabular numbers so their width stays stable.

Use a 4 px spacing base. Start with 8 px between related controls, 16 px within small groups, 24 px within content surfaces, and 40 to 64 px between major areas. Suggested radii are 8 px for controls, 12 px for sheets, and 20 px for occasional overlays. Nested radii should account for the surrounding padding.

## composition

On a wide screen, use a compact header and a reading canvas up to approximately 1280 px wide. The main thought column is about 640 to 720 px wide. A context margin of about 320 to 360 px appears when related information is surfaced. Give the composer or active exchange the strongest position and contrast.

Navigation should expose the current mode and a clear way to return to capture. Keep secondary destinations quiet. Do not add navigation categories that require the person to classify their thoughts manually.

On smaller screens, use one column with 16 to 20 px outer gutters. Surface context below its related passage or in an accessible sheet. Preserve the active input when context opens. The virtual keyboard must not cover the composer or recording controls, and closing a sheet must restore focus to its trigger.

## mode direction

### normal

The main surface receives typed or spoken thoughts with minimal ceremony. The composer remains available while confirmed results appear nearby. Live transcript text should stay readable as it settles, without moving older passages around unnecessarily.

When the person asks to revisit information, present a coherent concept cluster with readable summaries, related ideas, and access to the original words. Prefer a reading layout with relationships expressed as annotations. An optional spatial view may supplement it later.

### conversational

Use a readable sequence of exchanges, with a clear distinction between the person's words and vanille's responses. Keep the current input and speaking state visible. Retrieved concepts should appear as supporting context connected to the exchange that surfaced them.

Provide a visible transcript for spoken responses. Mode changes should be deliberate, with the current mode always identifiable. The behavior of switching during an active recording or exchange needs to be settled before implementation.

## component direction

| element | design requirement |
| --- | --- |
| thought composer | an inset writing surface with a persistent label and one clear primary action |
| recording control | an explicit action with readable listening, paused, and stopped states |
| source passage | original words with quiet speaker and time metadata |
| concept summary | a readable interpretation, visually distinct from its supporting source |
| context margin | relationships attached to the active thought, with restrained connectors and labels |
| mode control | two clearly labeled choices, with selection conveyed beyond color |
| status message | brief, specific language beside the action it describes |

Stored concepts are read-only in the interface. Draft input may be revised before submission. Future corrections and elaborations should flow through normal or conversational input, without inline concept editors or draggable organization controls.

## states and trust

Plan for idle, listening, transcribing, processing, saved, paused, empty retrieval, and failure states. These states must reflect the eventual service responses. Captured speech, interpreted concepts, and confirmed storage are different events. Show `saved.` only after persistence is confirmed.

Handle microphone permission denial, interrupted capture, unavailable audio output, connection loss, and processing failure with a clear next action. Preserve unsent text when an operation fails. Avoid invented progress percentages and animated success before an operation completes.

The empty state should invite a thought in one short sentence. Retrieval with no result should explain that plainly. Status uses text and a distinct visual treatment, so meaning survives without color or animation.

## motion and accessibility

Motion should explain focus and state changes while leaving the words stable. Start with 100 to 140 ms for press feedback, 140 to 200 ms for controls, and 180 to 260 ms for contextual surfaces. Use a deliberate ease-out curve such as `cubic-bezier(0.23, 1, 0.32, 1)`.

Use transform and opacity for movement. Keep typing and repeated actions immediate. Recording visualization should represent actual input when implemented. Under `prefers-reduced-motion`, remove spatial movement and retain immediate, readable state changes.

Use semantic controls, visible focus, keyboard access, persistent labels, and restrained announcements for recording or saving state. Prefer 44 by 44 px touch areas as a project usability target. Measure text contrast against the actual background, including overlays. Follow the [W3C text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), with at least 4.5 to 1 for ordinary text and 3 to 1 for qualifying large text. Target sizing must also meet the [W3C minimum target guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

## implementation boundaries and review

Next.js, React, and Tailwind are the foundation. Use Motion for ordinary interface transitions. Reserve GSAP for sequences that need coordinated timing. Three.js is optional and must have a readable, keyboard-accessible alternative if used for relationships. Libraries should serve an agreed interaction rather than define it.

Before implementing a screen, identify its focal action, reading hierarchy, states, and responsive behavior. Review at narrow mobile and wide desktop sizes, with long thoughts, empty results, failures, keyboard navigation, and reduced motion.

The design succeeds when entering a thought feels immediate, original words remain distinguishable from interpretation, surfaced context remains readable, and the interface communicates capture and storage honestly. Code execution, manual editing of stored concepts, and operational infrastructure views are outside the product experience.
