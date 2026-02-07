# Animation Setup in svg2ooxml

This document outlines the current setup for handling SVG (SMIL) animations within the `svg2ooxml` conversion pipeline, from parsing to conversion into PowerPoint's DrawingML timing XML.

## 1. Overview

The `svg2ooxml` project supports a significant subset of SVG SMIL (Synchronized Multimedia Integration Language) animations, including `animate`, `animateTransform`, `animateColor`, `animateMotion`, and `set` elements. The overall pipeline involves:
1.  **Parsing:** Extracting animation definitions from SVG DOM into a structured Intermediate Representation (IR).
2.  **Conversion:** Translating these IR animation definitions into PowerPoint's native DrawingML timing XML elements.

## 2. Intermediate Representation (IR)

The core animation IR is defined in `src/svg2ooxml/ir/animation.py`. Key data structures include:

*   **`AnimationType`**: An Enum (`ANIMATE`, `ANIMATE_TRANSFORM`, `ANIMATE_COLOR`, `ANIMATE_MOTION`, `SET`) categorizing the SVG animation element.
*   **`FillMode`**: Defines animation behavior after playback (`freeze` or `remove`).
*   **`TransformType`**: Specifies the type of transform animation (`translate`, `scale`, `rotate`, `skewX`, `skewY`, `matrix`).
*   **`CalcMode`**: Represents SMIL calculation modes (`linear`, `discrete`, `paced`, `spline`) for interpolation.
*   **`AnimationTiming`**: Stores `begin`, `duration`, `repeat_count`, and `fill_mode`, with helper methods for time calculations.
*   **`AnimationKeyframe`**: Represents an individual keyframe with `time`, `values`, and optional `easing` (cubic Bezier).
*   **`AnimationDefinition`**: The central dataclass for a single SVG animation, encapsulating `element_id`, `animation_type`, `target_attribute`, `values`, `timing`, `key_times`, `key_splines`, `calc_mode`, `transform_type`, `additive`, and `accumulate`. It includes `__post_init__` validation for consistency.
*   **`AnimationSummary`**: Aggregates statistics for all animations in an SVG, calculating an overall `complexity` score (Simple, Moderate, Complex, Very_Complex) based on factors like animation count, transforms, motion paths, easing, and duration.

## 3. Parsing (SVG to IR)

The `SMILParser` (`src/svg2ooxml/core/animation/parser.py`) is responsible for extracting animation elements from the SVG DOM and converting them into `AnimationDefinition` IR objects.

**Strengths:**

*   **Comprehensive SMIL Tag Support:** Recognizes all major SMIL animation tags.
*   **Detailed Attribute Parsing:** Handles `attributeName`, `values`, `from`, `to`, `begin`, `dur`, `repeatCount`, `fill`, `keyTimes`, `keySplines`, `calcMode`, and `type` for `animateTransform`.
*   **Timing and Interpolation:** Correctly parses time values, repeat counts, and fill modes. Supports `keyTimes` and `keySplines` for complex interpolations.
*   **Target Element Resolution:** Resolves animation targets using `href`, parent `id`, and `target` attributes.
*   **Motion Path Parsing:** For `animateMotion`, it parses `path` attributes or `<mpath>` elements.
*   **Robustness:** Includes error handling (`SMILParsingError`) and adds warnings to `AnimationSummary` for invalid formats.
*   **`AnimationSummary` Integration:** Populates `AnimationSummary` with metadata like total animations, duration, and presence of transforms/motion paths.

**Limitations/Areas for Review:**

*   **Complex `begin` Event Triggers:** Advanced `begin` values (e.g., `begin="click"`, `begin="id.begin + 2s"`) might not be fully supported; current parsing focuses on time values.
*   **`from/to/by` Attribute Combinations:** While `from` and `to` are handled, the `by` attribute and complex combinations of `from/to/by` might require further review.
*   **`calcMode="paced"` Nuances:** The parser captures `CalcMode.PACED`, but its accurate interpretation requires understanding actual distances between animation values, which is an implementation detail for later stages.

## 4. Conversion (IR to DrawingML/PowerPoint)

The `DrawingMLAnimationWriter` (`src/svg2ooxml/drawingml/animation/writer.py`) orchestrates the conversion of IR `AnimationDefinition` objects into PowerPoint timing XML.

**Architecture:**

*   **Element-Based Pipeline:** All handlers return `lxml.etree._Element` objects (not strings). The writer collects these elements, assembles the complete ECMA-376 compliant timing tree, and calls `to_string()` exactly once at the end. This eliminates fragile string→parse→graft patterns.
*   **Handler-Based Design:** Employs a modular system where specialized `AnimationHandler` implementations (e.g., `OpacityAnimationHandler`, `ColorAnimationHandler`, `MotionAnimationHandler`, `TransformAnimationHandler`, `NumericAnimationHandler`, `SetAnimationHandler`) are responsible for specific `AnimationType`s. Handlers are processed in priority order (specific to general).
*   **Dependency Injection:** Handlers receive `AnimationXMLBuilder`, `ValueProcessor`, `TAVBuilder`, and `UnitConverter` via constructor injection.
*   **Pre-Allocated IDs:** `TimingIDAllocator` pre-allocates sequential IDs for the entire timing tree (root=1, mainSeq=2, clickGroup=3, then animation pairs) before any handler runs. This guarantees unique, sequential IDs without mutable counters.
*   **ECMA-376 Compliant Timing Tree:** The writer builds a proper click group wrapper (`<p:par>` with `fill="hold"`) inside the mainSeq, matching the structure PowerPoint expects for auto-play animations.
*   **`AnimationPolicy` Integration:** Utilizes `AnimationPolicy` to make decisions on whether to skip an animation (e.g., due to high spline approximation error or unsupported features) and to manage fallback strategies.
*   **Tracing:** Integrates with `ConversionTracer` to log events (`fragment_emitted`, `fragment_skipped`) and metadata, aiding diagnostics.

**Key Components & Their Roles:**

*   **`AnimationXMLBuilder` (`xml_builders.py`):** Provides element-returning builder methods for PowerPoint timing XML structures (`build_timing_tree()`, `build_par_container_elem()`, `build_behavior_core_elem()`, `build_set_elem()`, TAV elements, etc.).
*   **`TimingIDAllocator` (`id_allocator.py`):** Pre-allocates all IDs for the timing tree in one call. Returns a `TimingIDs` dataclass with `root`, `main_seq`, `click_group`, and per-animation `(par, behavior)` ID pairs.
*   **`AnimationUnitConverter` (`unit_conversion.py`):** Centralized unit conversion with named constants (`PPT_ANGLE_FACTOR=60000`, `PPT_OPACITY_FACTOR=100000`, `PPT_SCALE_FACTOR=100000`) and methods for opacity, angle, EMU, scale, and slide-fraction conversions.
*   **`ValueProcessor` (`value_processors.py`):** Parses and normalizes animation values (colors, angles, scale pairs, translation pairs, opacity) for PowerPoint's specific requirements.
*   **`TAVBuilder` (`tav_builder.py`):** Builds Time-Animated Value (TAV) lists (`<p:tavLst>`) for multi-keyframe animations, handling `keyTimes` and `keySplines` (cubic Bezier easing) interpolation.
*   **`UnitConverter` (`common/units.py`):** Converts SVG units (e.g., pixels) to PowerPoint's internal EMU (English Metric Units).

**Handler Specifics:**

*   **`MotionAnimationHandler` (`motion.py`):**
    *   Handles `animateMotion` by generating `<a:animMotion>` elements with `<a:ptLst>` (point list).
    *   **Motion Path Parsing:** Uses `svg2ooxml.common.geometry.paths` to parse SVG path data.
    *   **Bezier Curve Sampling:** Discretizes Bezier curves into line segments (default 20 steps) to produce point lists suitable for PowerPoint.
    *   **Unit Conversion:** Converts path coordinates from pixels to EMUs.
*   **`TransformAnimationHandler` (`transform.py`):**
    *   Handles `animateTransform` animations.
    *   **Scale:** Generates `<a:animScale>` with `<a:from>` and `<a:to>` scale pairs (x, y).
    *   **Rotate:** Generates `<a:animRot>` with rotation delta. Converts angles to PowerPoint format.
    *   **Translate:** Generates `<a:animMotion>` with `<a:by x="..." y="..."/>` for simple translations, or `<a:ptLst>` for multiple translation keyframes.
    *   **Matrix Decomposition (`_classify_matrix`):** Attempts to decompose `animateTransform type="matrix"` into simpler `translate`, `scale`, or `rotate` components if possible, converting them to native PowerPoint animations. If not reducible, the animation is dropped.
    *   **`TAVBuilder` Integration:** Uses `TAVBuilder` for scale and rotate animations with `keyTimes` and `keySplines`.

**Critical Aspects & Limitations:**

*   **`calcMode="paced"` Implementation:** The exact mechanism for implementing `paced` interpolation in PowerPoint's animation model, especially for motion paths, may require further review.
*   **Complex `begin`/`end` Events:** Event-based or sync-based `begin`/`end` triggers from SVG/SMIL are generally not supported natively by PowerPoint and might be simplified or ignored.
*   **`animateTransform type="matrix"` (Skew/Combined Transforms):** While matrix decomposition handles simple cases, complex matrices involving skew or arbitrary combinations of transforms are likely not fully supported and may lead to the animation being dropped.
*   **SVG `rotate="auto"` in `animateMotion`:** This feature, where an element automatically rotates to follow the tangent of the motion path, is complex to replicate in PowerPoint and is not explicitly handled.
*   **`additive` and `accumulate` Attributes:** The precise translation of these attributes into PowerPoint's animation model for various animation types may have limitations.
*   **Rotation Around Custom Points:** SVG rotations can specify a center point; PowerPoint usually rotates around the shape's center. Custom rotation points might not be accurately converted.
*   **Visual Fidelity of Interpolation:** The accuracy of cubic Bezier `keySplines` approximation via `TAVBuilder` and Bezier curve sampling for motion paths determines visual fidelity. The `AnimationPolicy`'s spline error estimation helps manage this.
*   **Timeline (Scenes) Usage:** The `timeline` parameter is currently unused, potentially limiting the system's ability to handle highly complex, interdependent animation sequences where the precise state of elements across a global timeline is required.

## 5. Next Steps

Future work or critical review could focus on:
*   Implementing support for complex `begin`/`end` event triggers.
*   Improving handling of `calcMode="paced"`.
*   Developing more sophisticated fallbacks or approximations for unsupported `animateTransform` types (e.g., skew, arbitrary matrix combinations).
*   Enhancing `MotionAnimationHandler` to support `rotate="auto"` or `keyPoints`.
*   Investigating the exact behavior of `additive` and `accumulate` in PowerPoint and ensuring correct translation.
*   Exploring the use of the `timeline` for more accurate conversion of complex animation interactions.