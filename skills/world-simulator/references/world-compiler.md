# World Compiler

Use this guide for every Studio turn and for the `begin` transition.

## Purpose

Turn the user's language into a playable causal model, not a decorative lore dump. The result must support immediate scenes, future consequences, and natural revision without requiring the user to fill a form.

## Compile in This Order

1. Extract hard constraints: genre, tone, scale, player fantasy, boundaries, named facts, and requested exceptions.
2. Find the world's engine: what people want, what prevents them from getting it, what changes if nobody intervenes, and why the player can matter.
3. Reconcile gaps with the smallest useful assumptions. State material assumptions in the visible Studio response; do not bury them as settled canon.
4. Create or update stable records. Typical kinds include `player`, `scene`, `character`, `place`, `faction`, `rule`, `item`, `thread`, `quest`, and `threat`; these are vocabulary, not a mandatory schema.
5. Connect records with directed relations whose predicates say something operational, such as `owes`, `controls`, `hunts`, `protects`, or `located-in`.
6. Give active threats and threads a present condition, pressure, likely next development, and—when useful—a numeric `gm.next_due` turn.
7. Establish a player record and prospective scene as soon as the user's concept supports them. Keep unknown player details open rather than inventing a biography.

## Separate Public and GM Truth

Put established player-visible knowledge in `public`. Put secrets, concealed motives, unrevealed causes, future pressure, and adjudication notes in `gm`. Mark an entire entity or relation `visibility: "gm"` when even its existence is secret.

The Studio UI may show GM structure so the user can co-author the world. Once play begins, the API removes GM fields and GM-only records from the browser.

## Write the Studio Response

Summarize what the world has become in clear prose. Highlight the few assumptions or tensions that most affect play. Ask a natural open question only when its answer would materially reshape the world; do not emit a numbered setup wizard or a list of canned options.

Mark the few defining terms, assumptions, or sentences with `**bold**`. If the response contains spoken dialogue, bold the complete spoken line including its quotation marks. Keep ordinary supporting prose unbolded so the emphasis remains meaningful.

Revision is compilation, not append-only lore. When the user changes a premise, update every affected entity and relation so the ledger has one current truth. Retire obsolete relations explicitly.

## Begin Play

For a `begin` turn:

- apply any final instruction in the input;
- set `session.mode` to `play`;
- set valid `player_id` and `scene_id` values;
- open on a concrete situation already in motion;
- give the player sensory facts and meaningful room to act;
- avoid narrating the player's choice, feelings, or response.

The opening is the first play scene, not a recap followed by an action menu.
