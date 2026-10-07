vanille.

note taking at it's purest form.

what is vanille?:
vanille in simple terms is a note taking app. what makes it interesting though is that note-taking begins one step before normal journaling. when you typically want to write a tought down you need to find a way to translate what's in your head in speech that can be digestible by either future you or even others. what if you had a system that could take the messy brain spew you throw it, organizes it, optionally challenges you to elaborate further, and forms an idea of your concepts for you to review later. this is the broad concept of what vanille is supposed to be.

vanille is not or does not allow for:
 - editing stored concepts manually : in the best of worlds, the system should be able to be completely managed through the normal or the conversation mode ( to be expanded )
 - code tasks : writing prs, generating code, running tests. it can help with planning and defining architecture, but it is not meant to write anything.

color palette: beige, brown, white, onyx

stylistic decisions: lowercase, punctuation: ".,", 

architecture

vanille directory (and docker stack):
- frontmatter
 - next.js probably
 - react
 - tailwind
 - motion + gsap
 - three.js
- frontpage
 - vite
 - react
 - tailwind
 - motion
- backend
 - python?
 - typescript
- db
 - neo4j
 - python (sage memory module) 
.env
.gitignore
AGENTS.md

frontmatter:
 vanille user interface. main application to interact with the system, input form to type or talk info gets processed and stored inside of db 

frontpage:
 vanille landing page, should feel smooth, clean, funded, almost editorial. should convey a somewhat cloudy atmosphere glassmorphic a little or a play with blur. display clear motion use gsap as needed and motion. we want interactive element and movement when displaying capabilities for example moving demo where a chat is sent through a mock of the system. 

backend:
 vanille backend service, defines different agents, runs api server, stt and tts routes, main orchestrator for live actions and conversation. "intelligence layer"

db:
 long-term data storage solution for agent, db scopes memory agents, server for memory related tasks extraction and retrieval included. defines different memory agents and owns  memory intake. expected to be first or second biggest service in the stack

modes:

 normal : 
  speak your thoughts freely into a black box, listens and displays your spoken words being indexed into the system automatically. ask for information to be surfaced and system displays the right concept cluster.

 conversational : 
  speak to a realtime agent ( can be personalized or have different personality presets ), debate about subjects, discuss further and have the entire conversation be saved for later retrieval. requested surfaced information is spoken by the agent  
