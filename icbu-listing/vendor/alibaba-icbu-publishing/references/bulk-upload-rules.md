# Alibaba Bulk Upload Rules

Use this reference when generating or repairing Alibaba ICBU Excel upload workbooks.

## Goal

Produce files that are:

- direct-upload ready
- category-matched
- keyword-usable
- less likely to fail import
- less likely to receive poor product-quality scores

## Workbook Rules

- Use the correct current Alibaba template for the target category.
- Treat the exported template structure as locked:
  - do not add columns
  - do not delete columns
  - do not reorder columns
  - do not change hidden sheets, validations, comments, or workbook structure
  - do not repurpose custom-attribute slots unless that exact structure has imported successfully before
- Edit only value cells that belong to the template's intended fillable content.
- Fill every required `*` field.
- One file should usually contain one clear category.
- Default to `30 SKUs` when the user asks for a category batch unless the user gives a different count.

## Commercial Fields

Default only when the user has not provided better account-specific values:

- MOQ: use a realistic category-specific minimum; avoid fake low MOQs for heavy or custom goods
- pricing: prefer tiered prices instead of one fixed price
- quantity tiers: increase cleanly, such as `10`, `50`, `100`
- unit prices: normally decrease at larger quantities
- lead time: quantities and days must increase logically as volume grows

## Company And Detail Content

Use English copy for:

- supplier introduction
- company advantages
- factory or trading profile
- customization capability
- production workflow
- packaging and shipping
- FAQs

Do not leave company-image or detail-image modules empty if the template expects them.

## Image Groups

Alibaba can reject duplicated URLs across image groups. Keep separate URL pools for:

- product image group
- detail image group
- company image group

Main image rules:

- show one clear product entity
- avoid collage-style images
- avoid weak screenshots or blurry video grabs
- avoid generic factory photos as the main image
- make the image match the exact category and title

## Category Match

If Alibaba flags category mismatch, check all four together:

1. title
2. main image
3. attributes
4. template category

The listing should not look like one product category while being uploaded under another category.

## Final Validation

Before delivery, check:

- file count and naming order
- row count per file
- first-row required fields
- workbook template structure
- price tiers
- lead-time ordering
- image URL separation
- title, attributes, and category alignment
- whether the upload order is clear to the operator
