"""PPT 视觉风格注册表（自动生成，勿手改）。

来源：ppt-master 的 references/visual-styles/（19 种风格）。
重新生成：python scripts/import_visual_styles.py <visual-styles 目录>

**风格与配色正交**：风格只管形状语言 / 装饰密度 / 留白节奏 / 字体特征 /
纹理层次，**不携带任何 HEX 色值**；配色由 design-themes 的 236 个主题提供。
两者在生成时组合使用（如 github 配色 × swiss-minimal 风格）。
"""

from __future__ import annotations

VISUAL_STYLES: dict[str, dict] = {
    "blueprint": {
        "id": "blueprint",
        "label": "Schematic line work on dark paper, isometric, annotated",
        "label_zh": "工程蓝图",
        "category": "corporate",
        "summary": "Engineering schematic — thin line work on dark blueprint paper, isometric projection, technical-annotation language. Speaks like a drawing hung on a wall, not a marketing slide. For architecture walkthroughs, technical briefings, engineering whitepapers, systems explainers.",
        "shape": [
            "Shape language: thin single-weight line frames (no heavy fills); components drawn as outlined geometry; optional isometric / 3D-axonometric projection for structures. Slight or zero corner rounding.",
            "Composition geometry: let the schematic be the layout — a full-page annotated drawing as the skeleton with content hung on leader lines; a circular detail blow-up linked to its source; dimension-line brackets framing a hero figure; an isometric exploded stack for structure or sequence; a drawing-sheet title block anchoring one corner.",
            "Decoration: the engineering-drawing vocabulary — dimension lines, leader arrows, component codes, coordinate labels, a faint gridline backdrop under everything. Annotation *is* the decoration.",
            "Whitespace: the grid breathes through; let line work float on the dark field with measured spacing."
        ],
        "typography": [
            "Clean sans for labels and body; monospace for every component name / code / coordinate — mirroring how real technical docs read.",
            "Small, precise annotation type; wide tracking on coordinate / dimension labels. Restraint over emphasis."
        ],
        "color_usage": [
            "Dark paper field; a single line-color carries all the schematic line work (frames, connectors, edges); one spot accent marks the current state / key path / callout — the classic engineering-drawing convention of one highlight color.",
            "Everything else stays low-key line work. The accent appears at few points, high contrast."
        ],
        "texture": [
            "Flat line work, not material elevation. Depth reads from isometric projection and layered line weights, not shadows. Optional subtle corner vignette / accent glow on the dark paper — keep it faint."
        ],
        "paired_rendering": "blueprint",
        "illustration": "supportive",
        "illustration_note": ""
    },
    "brutalist": {
        "id": "brutalist",
        "label": "Newsprint density, ruled boxes, raw structure, flat",
        "label_zh": "粗野主义",
        "category": "editorial",
        "summary": "Brutalist editorial newspaper. Wall-to-wall small type, irregular column widths, heavy rule lines, raw structure on show. Reportorial and information-dense — for annual reviews, research digests, manifestos, editorial decks that flaunt density.",
        "shape": [
            "Shape language: favor hard-edged native contours, ruled boxes, thick black borders / cell frames, visible column dividers, brackets, block arrows, and raw stamps. Exact native shapes remain eligible when their semantic job fits; treat them with the same sharp print discipline. Corner radius `rx=\"0\"` — never rounded.",
            "Composition geometry: a masthead numeral or headline set so large it crosses column rules; one grid cell inverted to solid ink (light type on dark) as the focal cell; full-bleed rule bars slicing sections; a single rotated stamp-box breaking the grid at one deliberate point.",
            "Decoration: the grid itself is the decoration — masthead bars, rule lines, boxed pull-quotes, halftone fills. No gradients, no soft cards, no shadows.",
            "Whitespace: tight and deliberate — narrow margins, dense columns, a newspaper's packed rhythm. Density is the point; retain enough breathing room for hierarchy and readability without imposing a per-page count.",
            "Irregular multi-column layout (mixed column widths) over a uniform grid; asymmetry is intentional."
        ],
        "typography": [
            "Strong role contrast: a heavy display sans for headlines (poster-black weight), a serif character for column body, and monospace for figures / data can create the collision this style needs without imposing a family count.",
            "Small body size, high density; strong size jump between masthead headline and body. Flush-left columns, tight leading."
        ],
        "color_usage": [
            "Near-monochrome: ink-dark structure and type on a paper-light field; use a localized spot accent as punctuation, such as a masthead rule, key figure, or stamp.",
            "Color as punctuation, not fill. No color blocking, no gradients — the accent earns attention by scarcity."
        ],
        "texture": [
            "Strictly flat — no drop shadows, no elevation. Depth comes from rule weight and halftone texture, not material. Optional paper-grain / halftone `<pattern>` for a printed feel."
        ],
        "paired_rendering": "screen-print` / `editorial",
        "illustration": "supportive",
        "illustration_note": ""
    },
    "chalkboard": {
        "id": "chalkboard",
        "label": "Dark slate, chalk strokes, powdery pastel accents",
        "label_zh": "黑板",
        "category": "hand_drawn",
        "summary": "Classroom chalkboard — a dark slate field, soft chalk-stroke line work, powdery pastel accents. Nostalgic and instructional. For teaching decks, tutorials, school / academic content, retro-classroom atmosphere.",
        "shape": [
            "Shape language: chalk-stroke line work with slightly diffused, dry-medium edges; sketched boxes, brackets, arrows in chalk. When a mark must read as hand-drawn chalk, use a `<path>` with non-aligned points rather than a pristine primitive. Functional native contours remain eligible; keep their paint, weight, and hierarchy inside the chalkboard system.",
            "Composition geometry: one big chalk ring around the term that matters; a radial mind-map spreading from a central concept; a hand-drawn arc timeline sweeping the board; an oversized chalk bracket grouping half the page; a boxed corner note holding the takeaway.",
            "Decoration: underlines and emphasis marks; a few sprinkled chalk stars / dots. Blackboard pedagogy — organized sections, a clear central focus.",
            "Whitespace: the dark board reads as room; let chalk marks breathe rather than crowd."
        ],
        "typography": [
            "Hand-lettered chalk character for titles; legible body. Dry, nostalgic, classroom-warm."
        ],
        "color_usage": [
            "Dark slate field; off-white chalk carries most marks; the deck's colors appear as soft, powdery pastel chalk accents, used sparingly.",
            "Restrained and powdery — never saturated fills."
        ],
        "texture": [
            "Flat — depth from chalk-stroke weight, not material. Chalk-dust grain texture across the board is on-brand; no drop shadows."
        ],
        "paired_rendering": "chalkboard",
        "illustration": "core",
        "illustration_note": ""
    },
    "dark-tech": {
        "id": "dark-tech",
        "label": "Dark canvas, glow accents, geometric precision",
        "label_zh": "科技暗色",
        "category": "corporate",
        "summary": "Dark canvas, luminous accents, geometric precision. For tech, AI, dev tools, data products, launches.",
        "shape": [
            "Shape language: crisp geometry; thin glowing rules; hexagon / circuit / grid motifs used sparingly. Corners may be sharp or only slightly rounded.",
            "Composition geometry: a glowing diagonal circuit trace splitting the field; concentric orbit rings staging a central metric; a hexagon node cluster mapping components; an oversized low-opacity numeral or glyph floating behind the content layer; thin bracket frames zoning the page.",
            "Decoration: glow accents, fine grid backgrounds, monospace labels, node / connector lines. Restrained — precision over clutter.",
            "Whitespace: dark negative space reads as depth; let elements float on it."
        ],
        "typography": [
            "Clean sans for body; monospace for labels / figures / code cues. Wide tracking on small-caps labels.",
            "High-contrast hierarchy against the dark field."
        ],
        "color_usage": [
            "Dark background; a restrained set of luminous accents carries focus through glowing figures or active nodes while everything else stays low-key.",
            "The accent does the work of attention through localized, high-contrast use rather than a fixed point count."
        ],
        "texture": [
            "Depth via glow and layering on dark, not drop shadows. Outer glow / light strokes mark elevation; gradients stay same-hue and subtle."
        ],
        "paired_rendering": "digital-dashboard",
        "illustration": "sparse",
        "illustration_note": ""
    },
    "data-journalism": {
        "id": "data-journalism",
        "label": "Multi-column micro-charts, sidebars, source lines, dense",
        "label_zh": "数据新闻",
        "category": "editorial",
        "summary": "Bloomberg / Economist news-infographic — publication-grade information density: multi-column grids, inline micro-charts, data tables, editorial sidebars, source lines. Cool and restrained, read like a financial long-read rather than a keynote. For finance, market reviews, research, annual data reports, data-driven explainers.",
        "shape": [
            "Shape language: a dense multi-column grid carrying many small charts and data tables inline; editorial sidebars and pull-stats; hairline dividers; hero numbers; a running source / footnote line. Information density is the look — kept legible by a rigorous grid.",
            "Composition geometry: the chart as the page's spine — layout wraps the visualization instead of boxing it; a hero number at full column scale; a full-width spanner rule dropping into a stat band; a sidebar cut into the grid; small-multiple strips instead of one boxed chart.",
            "Decoration: minimal beyond the data — a single accent rule, sparing annotation. Charts and numbers are the visual interest, not ornament.",
            "Whitespace: tight but structured; the grid earns density without clutter."
        ],
        "typography": [
            "Serif headline / hero-number for authority × a clean sans or monospace with lining figures for numeric precision in tables and chart labels. Small captions and source lines; tight, deliberate hierarchy."
        ],
        "color_usage": [
            "A restrained field — light publication paper or dark graphite both fit (Economist vs Bloomberg-terminal); the deck's accent marks risk / key figures, an optional secondary distinguishes a second series; charts use tints of the same family, never a rainbow.",
            "Numbers are colored to *mean* (up / down / risk / focus), not to decorate."
        ],
        "texture": [
            "Flat, publication-grade — when either carries the relationship, favor hairline rules over heavy cards. Flatness governs visual weight, not contour vocabulary; outlined or compound page fields remain compatible. Optional scrim on any image; no glow, no decorative shadow."
        ],
        "paired_rendering": "editorial",
        "illustration": "sparse",
        "illustration_note": ""
    },
    "editorial": {
        "id": "editorial",
        "label": "Magazine hierarchy, rules & columns, serif/sans interplay",
        "label_zh": "杂志编辑",
        "category": "editorial",
        "summary": "Magazine-grade hierarchy. Columns, hairline rules, a serif / sans interplay, strong typographic structure. For finance, journalism, research, long-form analysis.",
        "shape": [
            "Shape language: a rectilinear editorial scaffold favors thin rules and column dividers over repeated cards. Outlined, compound, or exact native contours remain available when they clarify ownership, contrast, sequence, or emphasis; restraint controls their visual weight, not the contour vocabulary. Rounding, when used, stays visually minimal.",
            "Composition geometry: an oversized drop cap or numeral anchoring the page; a pull quote breaking across columns; a full-height vertical rule the content hangs from; an asymmetric column split instead of mechanically even columns; a figure deliberately crossing a column edge.",
            "Decoration: hairline rules, kickers / eyebrows, pull quotes, drop-style emphasis — typographic, not graphic. Sparing.",
            "Whitespace: structured by columns and baseline rhythm; comfortable but information-rich.",
            "Multi-column text flow where content suits."
        ],
        "typography": [
            "Serif / sans interplay: a serif for headlines or pull quotes against a clean sans body (or the reverse). Clear role contrast.",
            "Strong vertical hierarchy: kicker → headline → standfirst → body. Generous leading."
        ],
        "color_usage": [
            "Mostly monochrome text on a light field; a restrained accent may emphasize a rule, highlighted figure, or kicker.",
            "Restraint — color marks structure and emphasis, not decoration."
        ],
        "texture": [
            "Flat to barely-raised. Rules and whitespace separate content, not shadows. Shadow only on a genuine floating element."
        ],
        "paired_rendering": "editorial",
        "illustration": "supportive",
        "illustration_note": ""
    },
    "glassmorphism": {
        "id": "glassmorphism",
        "label": "Translucent glass panels, gradient light, floating depth",
        "label_zh": "玻璃拟态",
        "category": "corporate",
        "summary": "Frosted-glass SaaS — translucent layered panels, flowing gradient light, floating depth on a dark field. Future-tech, weightless, premium. For modern SaaS, fintech, health-tech, product launches, AI demos.",
        "shape": [
            "Shape language: visibly rounded translucent glass panels (low fill-opacity over the dark field) with bright hairline edges; layered, floating cards that imply blur and frost.",
            "Composition geometry: one hero glass panel set off-axis over a radial bloom; overlapping translucent discs building the focal cluster; a large glass ring encircling the key metric; panels stepped in depth to imply sequence; a diagonal light beam crossing the dark field.",
            "Decoration: soft radial light blooms in the background; thin luminous edge highlights along panels; restrained — the glass material is the decoration, not added ornament. Realize the radial bloom / glow halo as a `<circle>` / `<ellipse>` with a `<radialGradient>` fill, never a `rect rx=w/2` standing in for it.",
            "Whitespace: dark negative space reads as depth; let panels float on it with room to breathe."
        ],
        "typography": [
            "Clean modern sans; regular with selective bold; airy. Exact Light/Black requires a user-confirmed installed face. Headlines can carry a luminous gradient on the dark field."
        ],
        "color_usage": [
            "Dark field; the deck's colors read as luminous gradients flowing across panels and titles, low-opacity glass tints, and a subordinate neon accent. Color behaves like light through glass, not flat fill.",
            "Depth and hierarchy come from how brightly the glass glows, not from heavy saturation."
        ],
        "texture": [
            "Depth via translucency, layering, bright edge highlights, and soft background glow — not hard drop shadows. Smooth multi-stop gradients are intrinsic here (the one style where generous gradient use is on-brand); keep them luminous, not muddy."
        ],
        "paired_rendering": "glassmorphism",
        "illustration": "sparse",
        "illustration_note": ""
    },
    "ink-notes": {
        "id": "ink-notes",
        "label": "Pale field, black hand-ink, sparse semantic accent",
        "label_zh": "墨线笔记",
        "category": "hand_drawn",
        "summary": "Whiteboard-ink minimalism — a pale field, confident black hand-ink line work, sparse semantic color. Considered and manifesto-clear, the professional end of hand-drawn. For methodology, before/after essays, mindset-shift narratives, technical manifestos.",
        "shape": [
            "Shape language: hand-drawn line work with slight, intentional wobble — boxes, arrows, dividers and brackets sketched as if on a thoughtful whiteboard. When a mark must read as hand-inked, realize it as `<path>` / `<polyline>` with off-grid points rather than a pristine primitive. Functional native contours remain eligible; line defines structure, while repeated filled-card grids are not the defaul…",
            "Composition geometry: a circled central concept with branch arrows carrying the page; a hand-drawn Venn or overlap sketch as the argument; strike-through-and-replace geometry for before/after; one oversized bracket grouping the evidence under the claim.",
            "Decoration: minimal — a few doodle marks (stars, dashes, dots, underlines) for emphasis. Restraint is the look; clutter breaks the \"considered\" feel.",
            "Whitespace: generous and empty; the pale field carries most of the canvas, elements float with room around them."
        ],
        "typography": [
            "Hand-lettered / humanist character for titles — bold, slightly oversized, confident. Plain legible sans for body.",
            "Reads as written-by-hand-but-deliberate, not corporate-precise."
        ],
        "color_usage": [
            "Near-monochrome: ink-dark line work on a pale field carries the composition; the deck's accent remains a sparse semantic mark for risk, positive state, or emphasis.",
            "Color carries meaning, not decoration; use only the accents that signify something on the current page."
        ],
        "texture": [
            "Strictly flat — no shadows, no paper grain (the field stays clean). Depth reads from line weight and spacing alone."
        ],
        "paired_rendering": "ink-notes",
        "illustration": "supportive",
        "illustration_note": ""
    },
    "ink-wash": {
        "id": "ink-wash",
        "label": "Rice-paper whitespace, brush marks, seal accent, still",
        "label_zh": "水墨",
        "category": "hand_drawn",
        "summary": "New-Chinese ink-wash — a rice-paper field, vast literati whitespace, restrained brush marks, a single seal-stamp accent. Still, considered, Eastern. For cultural reading-shares, philosophy, heritage, self-cultivation, 新中式 narratives.",
        "shape": [
            "Shape language: minimal brush-stroke marks and hairline dividers; the occasional ink-dark block; a single seal-stamp (印章) square as a focal accent. Avoid repeated card / box grids so emptiness remains the structure. A mark intended as brush stroke or ink bleed uses an irregular `<path>` with uneven control points rather than an `<ellipse>` / `<circle>` standing in for a wash. Functional native con…",
            "Composition geometry: one broad brush sweep as the page's diagonal spine; an open ensō-like ring framing the core phrase; a vertical scroll band ordering a sequence; a low wash horizon with content floating in the emptiness above; the seal square placed to counterweight an asymmetric field.",
            "Decoration: almost none; what little appears reads as brush and seal. Asymmetric, scroll-like composition with deliberate off-balance.",
            "Whitespace: vast and intentional — the rice-paper field carries most of the page; a few elements float in great calm."
        ],
        "typography": [
            "Brush / serif character for titles (calligraphic, expressive) against a clean modern sans body — a Kai × Hei contrast axis. Large airy titles, generous leading, vertical rhythm welcome."
        ],
        "color_usage": [
            "A pale rice-paper field dominates; ink-dark carries type and the rare ink shape; a single warm seal-red accent appears at one key point — scarce, like a stamp on a scroll.",
            "Near-monochrome ink discipline — restraint is the aesthetic, not abundance."
        ],
        "texture": [
            "Flat — emptiness and brush weight carry depth, not shadow. Optional faint paper grain or low-opacity ink-bleed wash; no drop shadows."
        ],
        "paired_rendering": "ink-notes` / `watercolor",
        "illustration": "supportive",
        "illustration_note": ""
    },
    "memphis": {
        "id": "memphis",
        "label": "Clashing color blocks, geometric confetti, bold outlines",
        "label_zh": "孟菲斯",
        "category": "expressive",
        "summary": "Memphis / Pop — clashing color blocks, geometric confetti, bold outlines, 80s-revival exuberance. Loud and playful. For festivals, consumer brands, youth culture, launch hype, anything that wants energy over restraint.",
        "shape": [
            "Shape language: bold geometric primitives — circles, triangles, zigzags, squiggles, blobs — with thick dark outlines. Mixed corner radii allowed; playful inconsistency is on-brand.",
            "Composition geometry: a giant primitive bleeding off one edge as the backdrop; a diagonal two-color field split; a zigzag or squiggle band as the section divider; props scattered at angles around one dominant rotated frame or badge at the focal point.",
            "Decoration: scattered geometric confetti, color-block backings, pattern fills (dots / stripes), oversized punctuation. Generous decoration — but composed, not chaotic.",
            "Whitespace: energetic asymmetry; props float at angles. Still leave the focal content room to read against the noise."
        ],
        "typography": [
            "Display poster type for headlines (heavy, attention-grabbing); a neutral readable sans for body so density stays legible under the visual energy.",
            "Big, confident headline scale; tight to the artwork. Body kept clean and quiet by contrast."
        ],
        "color_usage": [
            "Multi-accent clash is the signature, but the light field and dark outlines remain visually dominant. Front a curated subset of the deck accents on each page instead of displaying the whole set by quota.",
            "A light field carries the noise; dark outlines anchor every shape so the clash reads as composed, not muddy. Disciplined exuberance, never rainbow soup."
        ],
        "texture": [
            "Mostly flat pop-art blocks; bold outlines do the separating, not shadows. Optional hard-offset (sticker / cutout) shadows for a retro pop feel — flat, not soft. Keep gradients rare."
        ],
        "paired_rendering": "flat",
        "illustration": "core",
        "illustration_note": ""
    },
    "paper-cut": {
        "id": "paper-cut",
        "label": "Layered cut-paper sheets, soft inter-layer shadow, tactile",
        "label_zh": "剪纸",
        "category": "expressive",
        "summary": "Layered paper-craft — scissor-cut shapes stacked in tactile layers, soft shadow where layers overlap. Warm, hand-made, child-friendly without being childish. For education, children's content, cultural / folk topics, festival, sustainability.",
        "shape": [
            "Shape language: forms defined by crisp, slightly-irregular cut edges (no outlines); simplified, stylized shapes that read as cut paper rather than illustration. A silhouette intended to read as hand-cut uses an irregular `<polygon>` / `<path>` instead of a pristine digital box. Functional native contours and deliberately machine-cut layers remain eligible inside the same paper system.",
            "Composition geometry: stacked wave sheets building the page bottom-up; a die-cut window revealing the layer beneath; one large cut disc (sun / moon) anchoring the composition; tabbed sheet edges ordering steps; a foreground frame layer with the content on the sheet behind it.",
            "Decoration: layering itself is the device — each element is a \"sheet\" stacked over the one beneath; small cut-out accents on the top layer.",
            "Whitespace: cozy, composed — the backing sheet shows through as breathing room."
        ],
        "typography": [
            "Clean friendly sans; warm, not severe. Titles can sit on a cut-paper banner shape."
        ],
        "color_usage": [
            "Each color reads as one sheet of paper — the primary is the dominant foreground sheet, the secondary the backing field, the accent a small top-layer cut-out.",
            "Layering and overlap drive emphasis more than proportion: even a small primary sheet in front of a large secondary reads as primary-led."
        ],
        "texture": [
            "Real layered depth — a soft, low-opacity drop shadow under cut layers is core here (the style where layered shadow is the point, not a violation). Matte paper grain on each sheet."
        ],
        "paired_rendering": "paper-cut",
        "illustration": "core",
        "illustration_note": ""
    },
    "photo-editorial": {
        "id": "photo-editorial",
        "label": "Full-bleed photography dominates, text points & captions",
        "label_zh": "摄影编辑",
        "category": "editorial",
        "summary": "Photo-led editorial — large full-bleed photography dominates the page, text points and captions. The big image speaks; words title it. Magazine photo-essay rhythm. For architecture, design, fashion, culture, photography-forward long-reads.",
        "shape": [
            "Shape language: large full-bleed / edge-to-edge image fields are the page's spine; text sits in restrained columns, caption blocks, kickers, or overlay headlines. Minimal chrome — the photograph carries the page.",
            "Composition geometry: an L-shaped text zone carved out of the full bleed; a headline straddling the photo edge; a diptych / triptych panel split; one floating caption card breaking the image boundary — moves that serve the photograph, never bury it.",
            "Decoration: thin rules, section numbering, small figure notes; nothing competes with the image.",
            "Whitespace: generous around text; the photo fills, the type breathes beside it. Asymmetric magazine composition."
        ],
        "typography": [
            "Editorial serif / CJK title × clean sans body; magazine-column cadence; small precise captions and figure notes. Words are concise — they point, they don't fill."
        ],
        "color_usage": [
            "The photograph carries the color; the text-side field stays a quiet neutral so imagery dominates; one restrained accent marks numbering, rules, or a key word.",
            "Deliberately understated on the type side — the image is the loudest element, by design."
        ],
        "texture": [
            "Flat — no decorative shadows. The one practical exception: a scrim gradient over an image where overlay text needs legibility. Photography supplies the texture."
        ],
        "paired_rendering": "corporate-photo",
        "illustration": "sparse",
        "illustration_note": ""
    },
    "pixel-art": {
        "id": "pixel-art",
        "label": "Strict pixel grid, blocky forms, limited palette, flat",
        "label_zh": "像素艺术",
        "category": "specialty",
        "summary": "8-bit retro game — strict pixel grid, chunky blocky forms, a limited palette, no anti-aliasing. Playful and nostalgic. For gaming decks, retro-tech decks, nostalgic or game-flavored education / entertainment.",
        "shape": [
            "Shape language: style-defining visible forms align to a pixel grid — blocky shapes, stepped edges, sharp transitions, no smooth curves; optional 1-pixel darker outlines for definition. Exact native presets remain eligible when their semantic contour survives this blocky treatment; otherwise use a faithful stepped construction.",
            "Composition geometry: a stepped pixel staircase as the divider; an oversized sprite anchoring the page; a HUD frame with corner brackets zoning content; a tile ground-band along the bottom edge; a pixel progress bar as the sequence device.",
            "Decoration: classic game framing — HUD bars, tile floors, sprite icons, chunky pixel borders. References NES / SNES / arcade composition.",
            "Whitespace: grid-disciplined; let blocks sit on clean tiled ground rather than crowd."
        ],
        "typography": [
            "Pixel / bitmap display character for headlines; keep body in a clean legible face — full-pixel body type strains at reading length."
        ],
        "color_usage": [
            "Colors used as palette slots: primary the dominant object, secondary the terrain / background, accent the highlights and markers; a darker shade of the primary serves as outline pixels.",
            "Flat blocks only — shading comes from palette layering (lighter top, darker bottom), never gradients."
        ],
        "texture": [
            "No texture beyond the pixel grid itself; strictly flat blocks. Depth reads from lighter-top / darker-bottom pixel shading, not drop shadows."
        ],
        "paired_rendering": "pixel-art",
        "illustration": "core",
        "illustration_note": ""
    },
    "sketch-notes": {
        "id": "sketch-notes",
        "label": "Warm paper, doodle line work, soft pastel blocks",
        "label_zh": "手绘笔记",
        "category": "hand_drawn",
        "summary": "Warm hand-drawn sketchnote — soft paper field, black ink doodle line work, gentle pastel blocks. The most approachable style, friendly over precise. For education, training, onboarding, science communication, knowledge content.",
        "shape": [
            "Shape language: rounded shapes drawn with a slight wobble; pastel block fills that slightly overshoot their outlines (hand-painted feel); simple cartoon icons. When a contour must read as doodled, draw the wobble as a `<path>` with non-aligned points rather than treating `<rect rx>` as hand drawing. Functional native contours remain eligible and may share the page with hand-drawn marks.",
            "Composition geometry: a wavy-arrow journey path structuring the whole page; a radial mind-map around a central doodle; a hand-drawn banner ribbon carrying the title; numbered circles hopping along a dotted route; one cloud frame around the idea that matters.",
            "Decoration: small doodles — stars, sparkles, dots, underlines — sprinkled sparingly for warmth; wavy hand-drawn arrows connecting ideas with short inline labels.",
            "Whitespace: airy and well-organized; generous gaps between elements keep it friendly, never dense."
        ],
        "typography": [
            "Friendly hand-lettered titles; clear humanist body. Warmth and legibility over corporate severity."
        ],
        "color_usage": [
            "Warm, soft paper field; the deck's colors rendered as gentle pastel tints inside the blocks rather than full saturation; one accent reserved for a key arrow or emphasis.",
            "Generous but gentle — soft tints, never high-chroma or rainbow."
        ],
        "texture": [
            "Flat 2D — sketchnote is intentionally flat. Optional subtle paper grain for warmth; no drop shadows."
        ],
        "paired_rendering": "sketch-notes",
        "illustration": "core",
        "illustration_note": ""
    },
    "soft-rounded": {
        "id": "soft-rounded",
        "label": "Rounded cards, gentle elevation, approachable",
        "label_zh": "柔和圆角",
        "category": "corporate",
        "summary": "Approachable and modern. Rounded cards, gentle elevation, friendly rhythm. For product, SaaS, training, consumer decks.",
        "shape": [
            "Shape language: visibly rounded rectangles, pill tags, and soft containers. Keep the radius family coherent deck-wide.",
            "Composition geometry: a large soft disc or blob bleeding off one edge as the color field; a pill chain or exact native `arc` / `blockArc` preset replacing the boxed step row; one hero panel overlapping a full-width tinted band; an oversized rounded numeral behind the point. Use a custom arc path only when the presets cannot faithfully express the intended contour. Cards are the container language,…",
            "Decoration: cards as the primary container; icon accents; numbered circles; gentle dividers. Moderate, in service of clarity.",
            "Whitespace: comfortable padding inside cards; even gutters; balanced rather than austere."
        ],
        "typography": [
            "Friendly sans (humanist or geometric); medium weights; clear but not severe hierarchy.",
            "Rounded, open letterforms suit; avoid condensed / industrial faces."
        ],
        "color_usage": [
            "Theme color used confidently on covers / chapter backgrounds; same-hue tints for card backings; accent for key figures.",
            "Warmer, more generous color use than swiss / editorial. Assign hues by semantic role and visual hierarchy; intentional multi-hue compositions remain valid."
        ],
        "texture": [
            "Gentle elevation: soft shadows on floating cards, subtle tints, and optional same-hue gradients. Keep the elevation hierarchy shallow and coherent; peer-grid cards stay flat."
        ],
        "paired_rendering": "flat",
        "illustration": "supportive",
        "illustration_note": ""
    },
    "swiss-minimal": {
        "id": "swiss-minimal",
        "label": "Grid-locked, sharp, aggressive whitespace, near-zero ornament",
        "label_zh": "瑞士极简",
        "category": "corporate",
        "summary": "Strict Swiss-grid discipline. Modular grid, sharp geometry, aggressive whitespace, near-zero decoration. The most restrained style — for high-end consulting, architecture, design firms, type-led decks.",
        "shape": [
            "Shape language: favor sharp, exact native contours, true circles, single-weight rules, and a small number of large geometric planes. Use square corners by default; any rounding stays barely perceptible. The full native vocabulary remains eligible when the selected contour stays purposeful, exact, and sparse.",
            "Composition geometry: one oversized geometric plane — a full-height color column, a giant disc, a heavy bar — zoning the page; an asymmetric split with content flush to one axis; a hero numeral at architectural scale; a single diagonal rule or type line as the deliberate grid break. Few, large, exact — geometry at poster scale is Swiss, clutter is not.",
            "Decoration: omit ornament without an information or composition job. No ornamental gradients, decorative blocks, or badges — structure carries the page. Content-bearing imagery, illustration, decorative lettering, and native geometry remain eligible when they strengthen that structure.",
            "Whitespace: vast and deliberate; negative space carries as much weight as content. Wide margins, generous gutters.",
            "Layout snaps to a visible or implied modular grid; rigorous column / row alignment."
        ],
        "typography": [
            "Sans-serif, single family; regular/bold contrast. Exact Light/Black requires a user-confirmed installed face. Tight, rigorous spacing.",
            "Strong size hierarchy — large headlines, small precise body. Left-aligned, flush."
        ],
        "color_usage": [
            "A dominant color may define a deliberate grid zone while the field stays near-white; keep accent color localized enough that it reads as punctuation rather than decoration.",
            "Color as conceptual zone, not decoration. No gradients."
        ],
        "texture": [
            "Strictly flat. No shadows, no depth, no material — 2D conceptual planes only."
        ],
        "paired_rendering": "minimalist-swiss",
        "illustration": "sparse",
        "illustration_note": ""
    },
    "vintage-poster": {
        "id": "vintage-poster",
        "label": "Mid-century flat blocks, halftone, retro-geometric warmth",
        "label_zh": "复古海报",
        "category": "expressive",
        "summary": "Mid-century print poster (1950s–1970s) — bold rounded-geometric shapes, limited flat color blocks, halftone / paper grain, retro warmth. For cultural decks, brand storytelling, hospitality, retro-tech narratives, anniversaries, heritage brands.",
        "shape": [
            "Shape language: bold geometric shapes with rounded organic edges, often slightly off-axis for retro tension; overlapping flat blocks; thick hand-aware lines; stylized, reduced iconography (a stylized sun, an angular mountain).",
            "Composition geometry: a giant sun disc or arch as the backdrop anchor; ray wedges radiating from the focal point; off-axis overlapping blocks staging the content; a horizon band splitting the page into field and sky zones; one badge or rosette seal at the emphasis point.",
            "Decoration: the print artifacts — halftone dot overlays, slight ink misregistration — carry the character. Generated illustration stays reduced and graphic. Required documentary photography remains eligible; integrate it through crop, tonal reduction, halftone, or another print treatment instead of replacing the real subject with invented imagery.",
            "Whitespace: confident poster composition — a few large blocks, deliberate negative space."
        ],
        "typography": [
            "Retro display character for headlines (mid-century geometric, confident); a simple legible body by contrast."
        ],
        "color_usage": [
            "Applied as limited flat blocks (a small set of colors): the primary dominates large blocks, the secondary reads as a warm paper field, the accent marks small shapes or tints the halftone.",
            "Flat color only — no gradients; depth comes from overlap, not blending."
        ],
        "texture": [
            "Flat — depth implied via overlapping shapes, never via shadow. Halftone dot pattern or paper grain at low opacity gives printed age; slight ink-offset character is on-brand."
        ],
        "paired_rendering": "vintage-poster",
        "illustration": "core",
        "illustration_note": ""
    },
    "zine": {
        "id": "zine",
        "label": "Riso misregistration, halftone, limited palette, print grit",
        "label_zh": "独立杂志",
        "category": "expressive",
        "summary": "Risograph zine / DIY poster — misregistered color layers, halftone dots, a tightly limited palette, handmade print grit. Indie-publishing texture over polish. For culture decks, design talks, indie brands, anything wanting a printed, hand-assembled feel.",
        "shape": [
            "Shape language: cut-and-paste blocks, offset color shapes, rough frames; outlines in a near-black ink tone. Corner radius low or zero — print-flat, not soft-digital.",
            "Composition geometry: rotated pasted-on blocks (slight skew) building the collage stage; a torn-strip band as the section divider; an oversized halftone shape bleeding behind the content; a photocopy frame or taped corner anchoring the focal block; column scraps at mixed widths.",
            "Decoration: the riso print artifacts — subtle visible color-layer misregistration, halftone-dot `<pattern>` texture, overlapping color blocks that imply another color where they cross. Texture is the decoration.",
            "Whitespace: poster-like — bold focal blocks with raw margins; deliberate roughness over clean alignment."
        ],
        "typography": [
            "Punk-DIY contrast: a heavy poster display face for headlines, a plain readable sans for body, monospace for annotation (typewriter / photocopier feel).",
            "Big headline tension against quiet body; slight intentional looseness reads as hand-set rather than mechanical."
        ],
        "color_usage": [
            "A tightly limited spot palette (riso logic) sits on a warm paper field; a dominant ink pairing does most of the work and any additional spot color appears selectively.",
            "Color is laid as flat spot fills, not gradients; overlap and offset of the same small ink set create depth and extra-color illusions. Scarcity and overlap, not variety."
        ],
        "texture": [
            "Flat print, no digital elevation. Depth from layer offset and halftone grain, not shadows. Warm-paper grain via faint texture / low-opacity halftone is on-brand; avoid drop shadows and slick gradients."
        ],
        "paired_rendering": "screen-print",
        "illustration": "core",
        "illustration_note": ""
    }
}


def list_styles() -> list[dict]:
    """给前端选择器用的精简列表（不含长文本规则）。"""
    return [
        {
            "id": s["id"],
            "label": s["label_zh"],
            "label_en": s["label"],
            "category": s["category"],
            "summary": s["summary"],
            "illustration": s["illustration"],
        }
        for s in VISUAL_STYLES.values()
    ]


def get_style(style_id: str | None) -> dict | None:
    """按 id 取完整风格；未知 id 返回 None（调用方应回退到默认）。"""
    if not style_id:
        return None
    return VISUAL_STYLES.get(style_id)


def style_prompt_block(style_id: str | None) -> str:
    """把风格渲染成注入模型的文案块（纯文本，不含色值）。"""
    style = get_style(style_id)
    if not style:
        return ""
    parts: list[str] = [f"### 视觉风格：{style['label_zh']}（{style['id']}）"]
    if style['summary']:
        parts.append(style['summary'])
    for key, title in (
        ('shape', '形状与装饰'),
        ('typography', '字体特征'),
        ('color_usage', '配色使用纪律（色值来自所选主题）'),
        ('texture', '纹理与层次'),
    ):
        bullets = style.get(key) or []
        if bullets:
            body = chr(10).join(f'- {b}' for b in bullets)
            parts.append(f'**{title}**' + chr(10) + body)
    return (chr(10) * 2).join(parts)
