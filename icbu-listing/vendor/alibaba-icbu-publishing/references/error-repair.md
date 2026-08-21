# Alibaba Import And Quality Error Repair

Use this reference when Alibaba ICBU reports import errors, quality-assistant warnings, category mismatch, or low product quality scores.

## Repair Process

1. Capture the exact Alibaba error text.
2. Identify the failure type before editing anything.
3. Repair the exact field group involved.
4. Compare the workbook against the last known import-success template when available.
5. Recheck required fields, image groups, category fit, pricing, and lead-time logic.

## Common Failures

### `仅支持xlsx/xls的格式`

Do not assume the extension is the real problem. First suspect:

- template-structure drift
- unsupported field-role changes
- hidden-sheet or validation damage
- exported workbook corruption from an incompatible editor

Repair by returning to a verified template and rewriting only safe value fields.

### `详情图集中存在图片和主图重复` or `公司图集中存在图片和主图重复`

Separate URLs across:

- main product images
- detail images
- company images

Fix by replacing URLs, not only reordering them.

### `物流属性缺失或者填写错误`

Check:

- logistics type
- freight template
- package length, width, height
- gross weight
- shipping model
- delivery setup

Heavy, fragile, oversized, or custom products need especially careful packaging values.

### `发货期必须由小到大`

Reorder quantity and day tiers so larger quantities do not have shorter or earlier lead-time logic.

### `类目错放`

Align:

- category template
- product title
- main image
- attributes
- use scene
- detail copy

Do not keep a title, image, or attribute set from one product category inside another category's template.

### Poor image quality or product quality score

Repair by:

- replacing weak main images
- making the product entity clear
- removing collage-style main images
- ensuring title and attributes clearly name the product
- matching detail images to the same category and buyer use scene

## Handoff

When reporting a repair, include:

- failure type
- fields changed
- remaining risk
- whether the file is ready to upload
- what the operator should check after import
