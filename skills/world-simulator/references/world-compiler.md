# World Compiler

Use this guide for Studio turns and the `begin` transition. Retain it in context while in that mode.

## Choose a Direction Worth Playing

Interpret the user's constraints, desired fantasy, tone, boundaries, named facts, and deliberate unknowns as a creative brief. Preserve the experience and degree of familiarity or novelty the user asked for.

Before writing canon, privately explore genuinely different directions that honor that brief. Do not expose the brainstorm or adopt the first idea merely because it is coherent, unusual, or easy to explain. Select, combine, and develop the direction that creates the strongest desire to enter the world and act within it.

Judge the direction from play outward. It should offer people with chemistry and conflicting wants, immediate situations with pressure and room for the player, and places, customs, institutions, or mysteries that can produce meaningfully different scenes. Its appeal should be tangible before the underlying lore is explained. A unifying concept earns prominence when it expands those possibilities; repeating the same motif through every power, secret, place, and character does not create depth by itself.

Privately audition the direction as an opening encounter and as unlike future situations. If its attraction depends on explaining the premise, or those situations collapse into repetitions of one device, deepen or replace the direction before committing it.

## Build a World With Breadth

Once the direction is worth playing, establish a rich setting early rather than delaying every fact until it appears on screen. Develop whichever geography, history, cultures, factions, institutions, important NPCs, relationships, secrets, conflicts, and opening pressures make this particular world coherent and playable.

Find the causal texture of the world: what its people want, what is in their way, what they misunderstand, what power structures shape them, what may change without the player, and why the player can matter. Connect these elements through consequences while retaining independent motives, histories, and sources of conflict. Prepare a living situation with many possible developments, not a predetermined plot or one thesis expressed at world scale.

Make useful assumptions when the concept leaves room. Surface only assumptions whose revision would materially change play. Accept revision naturally instead of running a setup questionnaire.

## Author Canon and Presentation Together

Store all canonical setting data in English:

- canonical entity names and Latin/English aliases;
- `public` and `gm` facts;
- relation predicates and facts;
- event summaries and data;
- the session narration profile.

For browser-label initialization or changes, consult [presentation-ui.md](presentation-ui.md).

Store the user's language and script separately under `presentation`. Localize names, aliases, kind and predicate labels, fact labels and values, the narration profile, the world title, and browser chrome. The localized layer expresses canon; it does not replace or reinterpret it.

Separate player-visible knowledge in `public` from concealed motives, causes, misconceptions, secrets, and unrevealed consequences in `gm`. During Studio the browser may show GM material for co-authoring. During Play the browser omits GM-only material.

## Establish Roleplay

Create the canonical session narration profile with free-form English prose fields:

- `role`: what kind of storyteller is speaking;
- `focalization`: whose perceptions and knowledge shape what can be told;
- `voice`: the narrator's personality, diction, distance, and attitude;
- `delivery`: how the voice handles pace, clarity, dialogue, action, reflection, and scene changes.

Give consequential NPCs enough inner structure to act rather than wait for plot instructions: desires, current intent, knowledge and misconceptions, secrets, relationships, emotional state, and speaking voice. These are semantic facts for Codex to interpret, not fields for Python to evaluate.

## Write the Studio Response

Tell the user what the world has become and which tensions or assumptions most affect play. Keep the visible explanation easy to grasp; do not dump every stored fact. Write clean prose without inline emphasis markup. Put the exact localized defining terms, material assumptions, revisions, or sentences that most affect play in `response.emphasis`. The browser emphasizes quoted dialogue automatically. Keep ordinary supporting prose unmarked so the reading hierarchy remains meaningful.

Revision changes the current truth. Patch all affected records and retire obsolete relations so the ledger does not contain competing versions.

## Begin Play

For `begin`:

- apply any final world instruction;
- set `session.mode` to `play`;
- set valid `player_id` and `scene_id` values;
- open on a concrete situation already moving;
- make the result, immediate reactions, and room to act legible;
- do not narrate the player's unsubmitted choice, feelings, or response.

The opening is a performed scene, not a lore recap followed by a menu.
