# 套图 skill

主 skill：https://github.com/buluslan/gpt-image2-ecommerce （312★，MIT）

国际站只用它的 6 个坑位模板，按它的规则把提示词写短：

| 坑位 | 模板 |
|---|---|
| 白底主图 | `01-hero-image.json` |
| 色号/规格平铺 | `03-flat-lay.json` |
| 尺寸 | `13-size-spec.json` |
| 细节 | `04-detail-macro.json` |
| 场景 | `02-lifestyle-scene.json` |
| 外箱 | `10-packaging.json`（改成出口纸箱，不用礼盒大理石） |
| OEM / 卖点 | `11-infographic.json`（不准编认证） |

拼词在 `server/services/ecom_skill.py`。类目套哪一组坑位仍在 `server/services/image_templates.py`。
