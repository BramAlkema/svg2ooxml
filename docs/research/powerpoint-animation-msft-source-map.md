# PowerPoint Animation Microsoft Source Map

This note collects the official Microsoft documentation that is actually useful
for PowerPoint animation reverse-engineering.

It is not an oracle.

It is a map of what Microsoft *does* document and, just as importantly, what it
still leaves undocumented for exporter work.

## Bottom Line

Microsoft documents PowerPoint animation across three layers:

1. Open XML / PresentationML overview docs
2. Open Specifications notes that describe PowerPoint-specific behavior
3. VBA / object-model docs that describe the authoring API

That is valuable, but it is still not the same as a UI-to-XML oracle.

What remains missing from Microsoft documentation is the exact authored
`p:timing` structure that PowerPoint emits for specific Animation Pane actions.

## 1. Open XML / SDK Layer

These docs explain the schema surface and SDK object model:

- Working with animation
  - <https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-animation>

What it gives us:

- where `p:timing` lives in a slide
- the core animation elements such as `anim`, `animMotion`, and target
  elements
- a schema-oriented view of PresentationML animation

What it does **not** give us:

- authored PowerPoint timing patterns
- trigger wrapper structures
- Animation Pane semantics

## 2. Open Specifications Layer

These pages are the most valuable official docs for our work because they add
PowerPoint-specific implementation notes on top of ECMA / ISO.

### Container and timing-node behavior

- `cTn` notes
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/9cc96243-2ada-46cc-9750-d8bdeb1fc2bb>

Useful for:

- `restart` defaults
- `display` meaning in PowerPoint UI terms
- `afterEffect` behavior
- triggered sequence requirement that `evtFilter` be `cancelBubble`
- `grpId` relationship to the build list

### Build-list behavior

- `bldP`
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/40d17b6d-30c0-4c10-b042-b2597824a820>
- `bldGraphic`
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/9ef2cc1c-86aa-4151-91fb-d0d761e4c7df>

Useful for:

- shape/build-list constraints
- uniqueness of `(spid, grpId)` pairs inside `bldLst`
- requirement that build-list references point to slide content and timing-tree
  groups that actually exist

### Attribute-name extensions

- `attrName`
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/baf99b7b-b2a7-44bb-a501-f6147d6c7123>

Useful for:

- PowerPoint-specific runtime properties like `ppt_x`, `ppt_y`, `ppt_w`,
  `ppt_h`, `ppt_c`, `ppt_r`, `fillcolor`, `r`, and related shear/scale names

### Motion behavior

- `animMotion`
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/498c3cfa-652c-49b3-a82c-33fd94468af8>
- `from`
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oe376/b4e7ea1e-7bb9-454d-96a3-61c6fcd0ea9a>

Useful for:

- PowerPoint defaults for `origin`
- path action semantics
- allowed property targets inside motion behavior
- coordinate interpretation details

### Rotation behavior

- `animRot`
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/39903f1a-fcb4-4aee-81e2-66f4fc7493fd>

Useful for:

- which attr names PowerPoint accepts for rotation animation

### Timing-tree structure

- `tnLst`
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-oi29500/55167345-00ff-4d39-b4a8-6ca61d86227a>

Useful for:

- PowerPoint restrictions on timing-tree structure compared with the broader
  standard

### Overall PowerPoint extension set

- `[MS-PPTX]` overview
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-pptx/b9ff79b4-5e24-4c85-b567-e5f43d498375>
- `[MS-PPTX]` spec root
  - <https://learn.microsoft.com/en-us/openspecs/office_standards/ms-pptx/efd8bb2d-d888-4e2e-af25-cad476730c9f>

Useful for:

- understanding that PowerPoint has a broader and more specific XML vocabulary
  than plain ECMA PresentationML alone

## 3. VBA / Object Model Layer

These docs tell us how PowerPoint exposes animation authoring through its own
API.

That matters because the object model is often closer to what the UI is doing
than the raw XML docs are.

### Sequence construction

- Main sequence
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timeline.mainsequence>
- Interactive sequences
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timeline.interactivesequences>
- Add effect
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.sequence.addeffect>
- Add trigger effect
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.sequence.addtriggereffect>

Useful for:

- distinguishing main-sequence effects from shape-triggered sequences
- understanding what PowerPoint considers a trigger effect at the authoring API
  level

### Trigger model

- `Timing.TriggerType`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing.triggertype>
- `Timing.TriggerShape`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing.triggershape>
- `MsoAnimTriggerType`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.msoanimtriggertype>

Useful for:

- page-click vs shape-click triggers
- target-shape-trigger semantics

### Timing controls

- `Timing` object
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing>
- `Timing.AutoReverse`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing.autoreverse>
- `Timing.RepeatCount`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing.repeatcount>
- `Timing.RepeatDuration`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing.repeatduration>
- `Timing.Restart`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing.restart>
- `Timing.Accelerate`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.timing.accelerate>

Useful for:

- auto-reverse
- repeat semantics
- restart semantics
- acceleration and deceleration controls
- trigger delay and timing properties in general

### Behavior collections

- `Effect`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.effect>
- `Effect.Behaviors`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.effect.behaviors>
- `AnimationBehavior`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.animationbehavior>

Useful for:

- understanding that one visible Animation Pane effect can correspond to
  multiple child behaviors

### Motion authoring API

- `MotionEffect`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.motioneffect>
- `AnimationBehavior.MotionEffect`
  - <https://learn.microsoft.com/en-us/office/vba/api/powerpoint.animationbehavior.motioneffect>

Useful for:

- PowerPoint's own coordinate-space model for motion
- behavior-level construction of paths and directional movement

## What Microsoft Still Does Not Really Give Us

Even after a broad official sweep, the following gap remains:

- there is no authoritative Microsoft page that says:
  - "click this Animation Pane command"
  - "PowerPoint will emit this exact `p:timing` tree"
  - "and it will round-trip this way"

Missing in practice:

- a UI-to-XML cookbook
- raw `p:timing` exemplars for specific effects
- pane-visible group/trigger recipes
- round-trip stability guidance
- a public oracle corpus of saved PowerPoint-authored animation XML

## Practical Conclusion

Official Microsoft docs are necessary but not sufficient.

They are best used for:

- schema boundaries
- PowerPoint-specific constraints and defaults
- object-model semantics

They are not enough for:

- choosing exact emitter templates
- reproducing Animation Pane grouping
- predicting save-roundtrip XML

That is why we still need our own XML-first oracle corpus on top of Microsoft
documentation.
