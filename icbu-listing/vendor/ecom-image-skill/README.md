# 套图提示词来源

从开源 skill 收了 6 个国际站用得上的场景模板（MIT）：

- https://github.com/liangdabiao/ecom-details-image
  `01-hero-image` `02-lifestyle-scene` `04-detail-macro`
  `10-packaging` `11-infographic` `13-size-spec`
- https://github.com/gpt-img-2/gpt-image-2-ecommerce-skill
  `prompt-patterns.md`（产品身份锁）

类目套图逻辑在 `server/services/image_templates.py`。没图时由平台用 Grsai `gpt-image-2` 按这 6 个坑位出图。

后来对照过的高星配方（只收规则，不收别人的图）：

- https://github.com/buluslan/gpt-image2-ecommerce （312★，灯光/构图写短、按类目加材质）
- https://github.com/gpt-img-2/ai-image-prompt-cookbook （83★，电商主图约束）
- https://github.com/motiful/product-shots （主图约 85% 画面、白底无字）
