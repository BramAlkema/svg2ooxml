# Documentation Guide

This repository contains converter-side documentation for `svg2ooxml`.
Empirical PowerPoint behavior research, authored control decks, and durable
oracle evidence live in the companion repository
[`openxml-audit`](https://github.com/BramAlkema/openxml-audit).
Figma and Google Slides app notes now live under
[`apps/figma2gslides/`](../apps/figma2gslides/README.md), including
app-owned docs and hosted legal pages.

## Start Here

- [README](../README.md) for installation, quick start, and project positioning
- [Testing guide](testing.md) for test tiers, visual tools, and W3C runs
- [Container workflows](guides/container-workflows.md) for the reproducible
  Docker render lane
- [Roadmap](ROADMAP.md) for current status and near-term priorities
- [Contributing guide](../CONTRIBUTING.md) for local workflow and review norms

## Find The Right Doc

- [Architecture decisions](adr/README.md) for stable converter-side decisions
  and rationale
- [Internal notes](internals/) for implementation snapshots and module
  maps
- [Repository boundary](internals/repository-boundary.md) for ownership rules
  between converter, app surface, and research
- [Animation documentation map](internals/animation-documentation-map.md)
  when the task touches animation support, fidelity, or validation
- [Specs](specs/) for target behavior, fidelity boundaries, and proposed design
- [Tasks](tasks/) for execution plans, blocker matrices, and phased follow-up
  work
- [Reference](reference/) for benchmarks, research notes, security notes,
  setup artifacts, and telemetry
- [Notes](notes/) for assessments, design notes, and issue investigations
- `_archive/` for retired material that should not be treated as current SSOT

## Folder Roles

- `docs/adr/` keeps stable decisions and the reasoning behind them
- `docs/internals/` describes current implementation structure
- `docs/specs/` defines intended behavior or fidelity targets
- `docs/tasks/` tracks ordered implementation work
- `docs/reference/` collects reference material and supporting evidence
- `docs/notes/` captures working analysis, design notes, and issue writeups
- `docs/guides/` contains operator and contributor how-tos
- `docs/_archive/` keeps superseded plans and historical notes out of the main
  path

## Animation Boundary

Animation docs were split so each layer has one job:

- [animation-system.md](internals/animation-system.md) describes the current
  module structure
- [svg-animation-native-mapping-spec.md](specs/svg-animation-native-mapping-spec.md)
  owns the conversion/mapping contract
- [powerpoint-fidelity-phase-2.md](specs/powerpoint-fidelity-phase-2.md)
  owns the broader fidelity program
- [animation-cleanup-rigour-spec.md](specs/animation-cleanup-rigour-spec.md)
  owns the cleanup direction

When in doubt, start with
[animation-documentation-map.md](internals/animation-documentation-map.md).
