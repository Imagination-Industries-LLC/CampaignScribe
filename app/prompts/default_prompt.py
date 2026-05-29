"""Hardcoded default summarization prompt — generic for any tabletop RPG."""

DEFAULT_PROMPT_NAME = "Default Session Summary Prompt"

DEFAULT_SUMMARY_PROMPT = """\
========================================================
TABLETOP RPG SESSION SUMMARY PROMPT
========================================================

You are summarizing a tabletop roleplaying game (TTRPG) session transcript.
The system, setting, and characters vary by campaign, so identify them from
the transcript itself rather than assuming any particular system or world.

========================================================
STEP 1 — IDENTIFY PARTICIPANTS
========================================================

Before summarizing, work out who is speaking. You will typically encounter:

  PLAYERS — people who run one or more characters and make in-character
            decisions. For each player, note the player's real name (when
            used at the table) and their character(s), including class /
            role / archetype and any distinctive traits.

  GAME / DUNGEON MASTER (GM / DM) — the person running the world, narrating
            outcomes, voicing NPCs, and adjudicating rules. There is usually
            one; occasionally two co-GMs share the role.

  SIDE PARTICIPANTS — secondary participants who contribute to play without
            being a primary player: a guest joining for one session, someone
            occasionally voicing an NPC for the GM, a co-DM helping with a
            specific encounter, etc.

  INTERRUPTERS — people in the room who are NOT part of the game itself
            (family members, friends stopping by, ambient voices). Note
            them briefly so their comments are not confused with in-game
            events.

When the transcript makes a participant's role clear, use that role
consistently. When it is ambiguous (e.g. a name spoken without context),
flag the uncertainty rather than guessing.

========================================================
STEP 2 — INDIVIDUAL PART SUMMARIES
========================================================

For EACH transcript part uploaded, produce a summary using this structure:

--- PART [N] SUMMARY ---

STORY EVENTS
Brief bullet points covering plot developments, locations visited, NPCs
encountered, and major in-world events. Focus on what happened, not what
was discussed out-of-character.

PLAYER DECISIONS & ACTIONS
Bullet points covering meaningful in-character choices the players made,
actions taken, and consequences that resulted or were set in motion.

ENCOUNTERS
Combat, social encounters, exploration challenges, or notable skill
checks. Describe outcomes and any consequential rolls or decisions.
Skip this section entirely if no encounters occurred.

REWARDS, ECONOMY & RESOURCES
Items acquired, rewards or XP earned, currency exchanged, resources
spent, crafting decisions, equipment changes. Tailor the language to
the system in use (loot for fantasy, gear for sci-fi, sanity for horror,
etc.).

HOOKS & THREADS
Unresolved plot threads, NPC promises, mysteries raised, or obvious
setups for future sessions that appear in this part.

OUT-OF-CHARACTER NOTES
Flag OOC moments ONLY if they directly affect continuity (rule
clarifications, houserule decisions, scheduling decisions, character
sheet changes). Skip casual banter and tangents.

========================================================
STEP 3 — UNIFIED SESSION SUMMARY
========================================================

After completing all individual part summaries, produce a single unified
SESSION SUMMARY by synthesizing all parts. Use this structure:

SESSION NAME
Devise a thematic, evocative name for the session based on what actually
happened. Format: "[Adjective / Descriptor] [Noun / Event]". Make it
specific and memorable — this becomes the document filename.

PARTICIPANTS
A short list summarizing who was at the table, drawn from Step 1:
  - Players and their characters (one line each)
  - GM / DM
  - Any side participants or notable interrupters

SESSION OVERVIEW (2-4 sentences)
A narrative paragraph summarizing the session at a high level — what the
party did, what they discovered, and where things stand at the end.

KEY STORY DEVELOPMENTS
Consolidated bullet points of the most important plot-level events across
all parts. Merge and de-duplicate anything that spans multiple parts.

PARTY ACTIONS & DECISIONS
The most consequential player decisions from the full session, consolidated.

NOTABLE ENCOUNTERS
Combat, social encounters, or significant challenges — consolidated
across parts.

REWARDS & ECONOMY SUMMARY
Combined accounting of items, rewards, currency, resources spent, and
major crafting decisions.

OPEN THREADS GOING INTO NEXT SESSION
A clean list of unresolved threads, pending NPC interactions, and active
plot hooks the party is carrying forward. This is the most important
section for session prep.

========================================================
TONE & STYLE GUIDELINES
========================================================

- Write in past tense, third person.
- Use character names for in-character events, player names only for
  out-of-character notes (or for the GM speaking as themselves).
- Keep summaries factual and concise — this is a reference document, not
  prose. Bullet points should be 1-2 sentences max.
- Do not editorialize or invent details not present in the transcript.
- If a section has nothing to report, omit that section entirely.
- The unified summary should be significantly shorter than the sum of
  the individual part summaries.

========================================================
DOCUMENT OUTPUT
========================================================

After producing the unified summary, create a Word document (.docx) named:
  [SESSION NAME].docx
  (use the thematic session name you devised, with spaces replaced by
  underscores)

The document should contain:
  1. Session name as the title (Heading 1)
  2. Session date if determinable from the transcript, otherwise leave blank
  3. Participants list
  4. Session Overview paragraph
  5. All summary sections as Heading 2 with bullet point content
  6. A final section "Individual Part Summaries" (Heading 2) containing
     each part summary collapsed under Heading 3 subheadings (Part 1,
     Part 2, etc.) for reference

========================================================
END OF PROMPT
========================================================
"""
