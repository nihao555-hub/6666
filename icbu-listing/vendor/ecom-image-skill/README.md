# 套图 skill

主 skill：https://github.com/buluslan/gpt-image2-ecommerce （312★，MIT）

国际站只用它的 6 个坑位模板。拼词按它 README 的原则，不堆关键词：

- **简洁为王**：只传核心信息，不过度约束
- **自然语言优先**：描述性句子优于关键词堆砌
- **材质描述**：明确写出纹理（磨砂玻璃、拉丝金属、哑光质感）
- **光照很重要**：始终包含光照方向和质感
- **善用参考图**：产品图走 `urls`，能显著提升一致性

| 坑位 | 模板 |
|---|---|
| 白底主图 | `01-hero-image.json` |
| 色号/规格平铺 | `03-flat-lay.json` |
| 尺寸 | `13-size-spec.json` |
| 细节 | `04-detail-macro.json` |
| 场景 | `02-lifestyle-scene.json` |
| 外箱 | `10-packaging.json`（改成出口纸箱，不用礼盒大理石） |
| OEM / 卖点 | `11-infographic.json`（不准编认证） |

卖家用中文、阿拉伯文或其他语言写品名时，先收成短英文名词再出图。商品上已有的印刷保留，不再叠别的语言。

拼词在 `server/services/ecom_skill.py`。类目套哪一组坑位仍在 `server/services/image_templates.py`。
