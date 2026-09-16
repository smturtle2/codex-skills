# Contributing

Keep each skill independently installable and the catalog easy to browse.

[Back to the catalog](README.md) · [한국어](CONTRIBUTING.ko.md)

## Runtime workspaces

Runtime-generated working files belong in the project-root-relative `.codex-skills/<skill-name>/<run-id>/` by default. An explicitly requested location wins, and existing older locations should be resumed in place without moving or deleting them. Create a workspace only when needed; retain resumable data and remove only expendable intermediates created by the current run. Final deliverables stay at the destinations requested by the user. The default Git ignore rule is `/.codex-skills/`; track data there only when the user intentionally asks for it.

Include this convention in each skill's own `SKILL.md` so it works when installed alone. Use a unique ID for new work and the same path for continuation. Pass the workspace to helpers and delegated work, align helper defaults and examples, and verify new runs, resume, and output destinations together. For world-simulator, the session ID is the run ID beneath `.codex-skills/world-simulator/`.

## Add a skill

1. Create `skills/<skill-name>/SKILL.md` with YAML frontmatter containing `name` and `description`. Use a lowercase, hyphenated name matching the folder. Describe when the skill should be used.
2. Bundle the scripts, references, and runtime assets it needs in that folder. Keep instructions concise and helper scripts locally auditable.
3. Optionally add user guides at `docs/skills/<skill-name>.md` and `docs/skills/<skill-name>.ko.md`. Start each with `# <skill-name>`, a blank line, and a short summary paragraph. Follow with installation, requirements, a usage example, and expected outputs.
4. Refresh the catalog from the repository root:

```sh
uv run scripts/update_catalog.py
```

Guides, screenshots, and custom icons are optional. A skill without a guide still appears with its `SKILL.md` description, a copyable install prompt, and a link to the instructions. When a Korean guide is missing, its catalog entry uses the original description until a translation is added.

The generator creates a consistent SVG header for each skill. It uses `assets/icon.svg` from the skill folder when available, or a shared module symbol otherwise. Colors are derived from the skill name, so adding or removing another skill does not change them.

## Update or remove a skill

Update the skill instructions and any affected guides together. If a guide exists, its first paragraph supplies the summary in that language's catalog.

To remove a skill, delete its folder, corresponding guides, and assets used only by those guides. Update references from other skills if needed, then refresh the catalog. The list is discovered from `skills/*/SKILL.md`, so a deleted skill disappears from both READMEs even if an old guide remains.

## Catalog maintenance

The generator updates only the region between `<!-- skills:start -->` and `<!-- skills:end -->` in each README, plus its own SVG headers in `docs/assets/catalog/`. It removes obsolete headers bearing its generated-file marker and leaves unmanaged assets alone. Edit the introduction and other sections normally; update the source descriptions or guides instead of editing generated entries.

The first `text` code block containing an install prompt in the English guide supplies the README install command for both languages, including companion skills. Without one, the generator supplies a single-skill install prompt.

To check whether the committed lists match their sources without writing files:

```sh
uv run scripts/update_catalog.py --check
```

This checks catalog and generated-header freshness only. Review changed links and relevant skill behavior separately, and state what you verified in your contribution.

Use Conventional Commits, such as `docs: add a usage guide` or `feat: add a skill`. Keep unrelated changes out of the contribution.
