# frontpage design.

## status and purpose

This is the design brief for vanille's landing page, based on [bootstrap.md](../bootstrap.md). The current page implements the editorial layout and animated, illustrative examples of planned capabilities. Live recording, conversation, and memory behavior remain future work. This document guides the page's continued design.

The visitor recognizes the problem of having an idea before having the words or structure to record it. The page should make vanille's purpose understandable, show how a rough thought can become something worth revisiting, and lead clearly into the application when that experience exists.

The direction is a warm editorial page with a cloudy atmosphere. Typography, considered proportions, open space, and precise movement should provide its confidence. The page should feel calm enough to read and active enough to explain the product.

## narrative and signature

The story is simple. A thought arrives in fragments. The person can express those fragments. Vanille helps organize their meaning. Related concepts can be revisited later, with the original words available as context.

The signature demonstration follows one rough thought from an input passage into a readable group of related concepts. Keep the same words traceable throughout the sequence. The visual can gradually settle into order, while the source passage retains its identity.

Use metaphors from paper, ink, margins, clouds, and recollection. The atmospheric blur belongs behind the content. The thought itself should become clearer as the visitor moves through the page.

## shared identity

Use the same core palette and proposed type families as the [frontmatter brief](../frontmatter/design.md). The landing page has a larger type scale, more space, and more expressive demonstrations. The application remains the quieter member of the same family.

| existing primitive | value | intended use |
| --- | --- | --- |
| `--color-beige` | `#f3eadc` | dominant page ground |
| `--color-brown` | `#6b4f3a` | supporting copy, fine details, selected emphasis |
| `--color-white` | `#ffffff` | soft light, clear reading surfaces, restrained glass |
| `--color-onyx` | `#242321` | headlines, body text, primary actions |

Use tints and transparency from these four colors. Avoid unrelated accent hues. Semantic roles should refer back to these existing primitives, so the two services retain a consistent identity.

White haze over beige can create the cloudy atmosphere. Keep it broad and low in contrast. A few translucent surfaces may use faint brown edges and soft depth, with an opaque fallback. Text sits on a stable background with measured contrast. Blur should not soften type or hide the product demonstration.

Brand and interface copy are lowercase, with periods and commas as the preferred punctuation. Preserve quoted source text as written. Keep the wordmark `vanille.` simple and typographic.

## typography and proportions

The page uses [Newsreader](https://github.com/productiontype/Newsreader) for display and editorial headings, and [IBM Plex Sans](https://github.com/IBM/plex) for body copy, controls, and demonstration text. Local WOFF2 assets and their licenses are included in `public/fonts/`, with readable system fallbacks.

| role | wide screen starting size | narrow screen starting size |
| --- | --- | --- |
| hero headline | 80 to 120 px | 44 to 64 px |
| section heading | 40 to 56 px | 28 to 36 px |
| lead paragraph | 20 to 24 px | 18 to 20 px |
| body copy | 16 to 18 px | 16 to 18 px |
| labels and captions | 12 to 14 px | 12 to 14 px |

Adjust headline sizes to their actual length. Use balanced wrapping and deliberate line breaks. Large type can use slightly tighter tracking and line height, while paragraphs keep a comfortable reading rhythm and a width around 55 to 65 characters.

Use a 4 px spacing base. Start with a page width around 1280 px, desktop gutters of 40 to 64 px, mobile gutters of 20 px, and 96 to 160 px between major desktop sections. On mobile, reduce section gaps to about 56 to 88 px. Related elements should feel close; different ideas should have room between them.

## proposed page sequence

| section | composition | message and behavior |
| --- | --- | --- |
| opening | centered editorial headline in a broad field of beige and white haze | establish `note taking at its purest form.` and explain the rough-thought premise in one short paragraph |
| thought demonstration | a wide central stage with the input passage and emerging concepts | show the same illustrative thought being captured, organized, and made available to revisit |
| two modes | two restrained text columns with distinct interaction examples | contrast normal capture with conversational exploration through clear, concrete behavior |
| recollection | a readable concept passage with related ideas in its surrounding margin | show why the result is useful later, including its connection to the original words |
| closing | a short statement, a clear app entry action, and a quiet footer | give the visitor a direct next step without introducing another visual concept |

Keep one focal element in each section. Vary the composition through the sequence. The demonstration should occupy enough space to be understood, while mode explanations and recollection can use more intimate reading layouts.

The main call to action should eventually open the real application entry. A secondary action may lead to the demonstration. Signup, waitlists, pricing, downloads, and their destinations need a separate product decision before they appear. Local development serves this page on port 9100 and the application on port 9101; production links remain undecided.

## demonstration direction

Use a short, believable example of an unfinished idea. The sequence should show the input, a clear organizing transition, and a final concept group with visible source context. Avoid exposing agents, database nodes, API calls, or other infrastructure in the visitor's explanation.

Any mock sequence must be labeled as an example. Its timing is illustrative and must not imply measured processing speed. Give the visitor a clear way to start or replay it and a readable final state. Do not require typing, microphone access, or submitting personal information to understand the demonstration.

For normal mode, show thoughts being received and useful context being surfaced. For conversational mode, show an exchange that helps elaborate an idea and a readable record of that exchange. Include the distinction that surfaced information can be spoken in conversational mode, with a visible transcript rather than automatic audio playback.

Describe capability honestly for the actual release. The page must not imply that the current bootstrap already provides these experiences. Avoid fabricated testimonials, usage metrics, funding claims, or promises about privacy and accuracy that have not been established.

## motion direction

Motion should explain the movement from fragments into concepts. Let source words settle, reveal their related labels, and bring the resulting group into a stable reading arrangement. Keep meaning visible throughout.

| use | starting timing | requirement |
| --- | --- | --- |
| button and link feedback | 120 to 180 ms | immediate and subtle |
| content entrance | 400 to 650 ms | small translation and opacity, with restrained stagger |
| demonstration step | 600 to 1000 ms | deliberate sequencing with time to read each result |
| ambient atmosphere | static by default | any later movement stays peripheral and pauses outside the viewport |

Use a consistent ease-out curve such as `cubic-bezier(0.23, 1, 0.32, 1)` for entrances and a smooth ease-in-out for movement already on screen. Prefer transform and opacity. Avoid animated blur or layout properties, scroll hijacking, mandatory pinned sequences, and entrances that hide content if scripting fails.

Reduced motion should show the complete narrative through static states and immediate transitions. A demonstration can advance in readable steps without spatial animation. Its meaning must not depend on scroll speed, hover, sound, or pointer position.

## responsive behavior and accessibility

On mobile, preserve the reading order and headline emphasis. Stack the mode examples, move margin annotations beneath their related passage, and simplify the demonstration into clear sequential states. Reduce ambient effects before reducing text size or touch areas. Keep the primary action easy to find without covering the content.

Use semantic sections and headings, keyboard-accessible links and controls, visible focus, and clear labels. Prefer 44 by 44 px touch areas as a project usability target, while meeting the [W3C minimum target guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html). Maintain at least 4.5 to 1 contrast for ordinary text and 3 to 1 for qualifying large text, following the [W3C contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

Readable content must survive unavailable blur, disabled animation, blocked fonts, and a narrow viewport. Provide text equivalents for visual demonstrations. Do not autoplay speech. Ensure moving demonstrations can be paused or replaced by their static explanation.

## implementation boundaries and review

Vite, React, and Tailwind are the foundation. Motion is already installed and should handle ordinary transitions and demonstration states. GSAP is optional for a sequence that needs more coordination; it is not currently a dependency of this service. Add libraries or assets only when implementation is requested and their role is clear.

Reserve image and video assets for material that supports the story. The initial direction can be expressed through typography, CSS atmosphere, and readable demonstration elements. Do not invent a logo, generate decorative AI imagery, or introduce a collection of stock illustrations to fill space.

Before implementation, settle final copy, font assets, the example thought, demonstration controls, and the actual app entry destination. Review the page at narrow mobile and wide desktop sizes, with keyboard navigation, reduced motion, long copy, and visual effects disabled.

The design succeeds when a visitor understands why an unfinished thought belongs in vanille, sees how its meaning can become useful later, and can identify the next action. The atmosphere should make that story easier to absorb.
