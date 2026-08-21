# Product-preserving prompt patterns

These patterns reflect two useful principles from OpenAI's current image guidance: state constraints explicitly, and describe both the requested change and the invariants when editing. Adapt every pattern to the actual brief.

Official references:

- https://developers.openai.com/api/docs/guides/image-generation
- https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide

## Product identity lock

```text
Use the supplied product reference images as the only source of truth for the product. Preserve [observable geometry], [real colors], [materials and finish], [label and logo positions], [controls/openings/ports], and [included-item count]. Do not redesign the product, infer unseen structure, add accessories, rewrite packaging, or introduce claims, certifications, functions, or marks that are not in the supplied evidence. The only allowed changes are [allowed changes].
```

Replace every bracket with product-specific facts. If a fact is unknown, omit the claim or request evidence.

## Clean hero / white-background main image

```text
[Product identity lock]

Create a clean ecommerce hero image whose single job is immediate product identification. Show the complete product at [supported view], centered, occupying about [subject occupancy] of the frame. Use a plain opaque white background, controlled studio light, a subtle physically plausible contact shadow, crisp edges, and accurate color and material rendering. No props, text, badges, border, watermark, or extra items. Output [aspect ratio].
```

## Lifestyle context image

```text
[Product identity lock]

Place the product in [realistic use environment] to demonstrate [one verified use]. Keep the product as the primary subject and preserve plausible scale, contact, reflections, and light direction. Supporting objects may establish context but must not obscure the product or imply included accessories. Reserve a clean copy-safe area on [side]. No generated copy, badges, or unsupported performance effects. Output [aspect ratio].
```

## Visible feature / material detail

```text
[Product identity lock]

Create a close product photograph focused only on [visible feature or material]. Show evidence visible in the supplied references; do not invent internal structure or magnify a texture beyond what the evidence supports. Use [macro/detail camera language], restrained light, accurate finish, and shallow depth only if the feature remains clear. No labels or callout text. Output [aspect ratio].
```

## Feature graphic with downstream typography

```text
[Product identity lock]

Build an unlettered base image for the verified message “[user-supplied claim]”. Communicate the use through composition rather than invented symbols or data. Keep [copy-safe area] visually quiet for later typesetting. Do not render copy, numbers, certification marks, comparison charts, or UI. Output [aspect ratio].
```

## Focused revision

```text
Change only [one correction]. Keep the product geometry, proportions, color, material, label and logo positions, controls/openings/ports, accessory count, camera position, crop, background, lighting, shadows, and all other visible elements unchanged. Do not regenerate or reinterpret the rest of the scene.
```

List only invariants that are actually visible and relevant. A focused revision should not become a contradictory wall of boilerplate.
