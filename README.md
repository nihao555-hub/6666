# TikTok 爆款带货视频数据集

通过 [TikHub API](https://api.tikhub.io) 爬取的 TikTok 爆款带货/工厂类视频。

## 筛选标准
- 点赞数 (likes) ≥ 10,000
- 评论数 (comments) ≥ 2,000
- 共 **481 个视频**，覆盖 20 个品类（含工厂宣传/探厂类 Factory 77 条）

## 目录结构
- `viral_videos.csv` / `viral_videos.json` — 全部元数据（赞/评/转/播放/收藏、作者、描述、是否挂购物车锚点、TikTok 原始链接、本地文件路径），按点赞数降序
- `videos/<品类>/` — MP4 视频文件，文件名格式 `{点赞数}likes_{评论数}cmt_{视频ID}.mp4`
- `scripts/` — 爬取脚本（crawl_fast.py 并发搜索+下载，backfill.py 补下载，normalize.py 品类归一化）

## 品类分布
Baby 23 · Beauty 36 · Car 8 · Cleaning 7 · Electronics 40 · Factory 77 · Fashion 32 · Fitness 31 · Food 23 · Hair 25 · Health 11 · Home 63 · Jewelry 6 · Kitchen 17 · Misc 5 · Office 6 · Outdoor 19 · Pets 22 · Shoes_Bags 7 · Toys_Gifts 19

## 使用脚本
```bash
export TIKHUB_KEY=<your_tikhub_api_key>
python3 scripts/crawl_fast.py
```
