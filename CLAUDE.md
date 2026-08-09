# Project rules

Spec: PRD.md. Design brief: design/DESIGN_HANDOFF.md.
Re-read the relevant PRD section before starting any new component.

- PRD §0 is a correction log of bugs from an earlier draft. Do not reintroduce them.
- Never import or serve anything from design/ — those are reference crops with UI baked in.
- Every node gets the @traced decorator from commit one.
- External web text goes in <fetched_content> tags in a user turn, never a system prompt.
- Pin versions per PRD §2. Freeze lockfiles, commit them.
- Ask before deviating from the spec.