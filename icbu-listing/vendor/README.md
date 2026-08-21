# vendor

官方完整 SDK 需要登录开放平台控制台、按当前 AppKey 的权限包生成，无法从公网固定 URL 拉取。

请把控制台下载的 zip 解压到 `official-sdk/`。本目录只放官方包，不要放淘宝客 `topsdk`。

当前发品链路不依赖这些类文件，走 `backend/top_client.py` 的官方 HTTP 协议即可。
