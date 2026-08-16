# 套图提示词来源

从开源 skill 收了 6 个国际站用得上的场景模板（MIT）：

- https://github.com/liangdabiao/ecom-details-image
  `01-hero-image` `02-lifestyle-scene` `04-detail-macro`
  `10-packaging` `11-infographic` `13-size-spec`
- https://github.com/gpt-img-2/gpt-image-2-ecommerce-skill
  `prompt-patterns.md`（产品身份锁）

本平台只用提示词，不代生图。类目套图逻辑在 `server/services/image_templates.py`。
