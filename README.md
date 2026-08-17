# TikTok 爆款带货视频数据集

通过 [TikHub API](https://api.tikhub.io) 爬取的 TikTok 爆款带货/工厂类视频。

## 筛选标准
- 点赞数 (likes) ≥ 10,000
- 评论数 (comments) ≥ 2,000
- 共 **1000 个视频**，覆盖 20 个品类（含工厂业务介绍/探厂/生产线类 Factory 162 条）

## 目录结构
- `viral_videos.csv` / `viral_videos.json` — 全部元数据（赞/评/转/播放/收藏、作者、描述、是否挂购物车锚点、TikTok 原始链接、本地文件路径），按点赞数降序
- `videos/<品类>/` — MP4 视频文件，文件名格式 `{点赞数}likes_{评论数}cmt_{视频ID}.mp4`
- `scripts/` — 爬取脚本（crawl_fast.py 并发搜索+下载，backfill.py 补下载，normalize.py 品类归一化）

## 品类分布
Baby 44 · Beauty 59 · Car 50 · Cleaning 17 · Electronics 45 · Factory 162 · Fashion 40 · Fitness 48 · Food 81 · Hair 47 · Health 38 · Home 75 · Jewelry 12 · Kitchen 33 · Misc 40 · Office 30 · Outdoor 36 · Pets 62 · Shoes_Bags 16 · Toys_Gifts 65

注：超过 GitHub 100MB 限制的少数视频已用 ffmpeg 压缩。

## LINE 多账号托管教程

LINE 后台操作说明（按官方文档）：[docs/line-multi-account/index.html](docs/line-multi-account/index.html)。

## 使用脚本
```bash
export TIKHUB_KEY=<your_tikhub_api_key>
python3 scripts/crawl_fast.py
```
