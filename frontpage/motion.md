# frontpage motion plan.

The landing page uses rich motion to explain the planned product, with quiet reading surfaces between sequences. Native scrolling stays in control. Motion for React supplies physical springs, viewport reveals, and finite example sequences. There are no input forms, microphones, live processing, or audio.

## coverage and choreography

| elements | trigger and order | motion |
| --- | --- | --- |
| wordmark, navigation, motion control | load, 0 to 160 ms | small spring arrival, underline and pressure feedback |
| hero label, headline, paragraph, action | load, 80 to 320 ms | masked line reveal, supporting spring entrances, button pressure |
| hero source fragments and atmosphere | load, then viewport | staggered arrival, slow peripheral drift that can be paused |
| section labels, headings, paragraphs | 15 percent visible, 0 to 160 ms | one consistent 550 ms spring reveal |
| rules and section indexes | with their section | scale from the left, opacity arrival |
| source passage and thought labels | example in view | readable fragments settle into a stable passage |
| source highlights, connecting threads, concept sheets | finite example sequence | source phrases emerge as related concepts, then settle |
| normal mode example | example in view | a finite waveform and source-to-context sequence |
| conversation example | example in view | staggered transcript exchange, ending in a readable record |
| recollection sheet and margin notes | section in view | paper arrival, connecting lines draw, notes settle |
| closing statement, action, footer wordmark and links | section in view | masked heading, staggered spring entrance, underline feedback |

Entrances use a snappy spring, mass 1, stiffness 400, damping 30. State changes use stiffness 200 and damping 24. Feedback uses a 160 ms custom deceleration curve. Entry delays end at 320 ms and spring visual duration is 450 to 600 ms. Example reading holds last longer than the actual 600 ms movements.

## example and accessibility

One invented thought about a small neighborhood reading room remains traceable through capture, organization, conversation, and recollection. Every illustration is explicitly an example of a planned capability. Sequences run once on entering the viewport and preserve their final state. Motion pauses out of view, when the browser tab is hidden, and through the page motion control. The example can be replayed without supplying any personal information.

Reduced motion presents complete example states immediately. It removes translation, scale, parallax, and ambient movement. Reveals become short opacity changes. Meaning is carried by readable text, never by animation alone.

## assets

Newsreader and IBM Plex Sans are self-hosted Latin WOFF2 subsets from Google Fonts. Original licenses are included in `public/fonts/`. The page uses typography, CSS light, and original SVG line work rather than generated images or stock illustrations.

## review

Verify desktop and narrow mobile layouts, native anchor navigation, keyboard focus, pause and replay, viewport suspension, reduced motion, blocked fonts and effects, and the absence of horizontal overflow. Typecheck, lint, and production build are required. Browser validation should report actual observations rather than assume a frame rate from implementation choices.
