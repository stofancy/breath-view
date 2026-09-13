# 外网入口

- Cloudflare：`sleep.ztmdsbt.site` A → `18.136.138.12`，仅 DNS，避免代理上传上限影响 ZIP。
- LightSail SSH：`sgrelay`；Nginx 配置 `/etc/nginx/conf.d/sleep.ztmdsbt.site.conf`。
- HTTPS：Let's Encrypt webroot `/var/lib/letsencrypt`；复用现有 certbot renew 定时任务和 reload-nginx hook。
- 回源：LightSail → Tailscale `100.120.30.7:8765` → NAS `192.168.0.118:8765`。
- NAS：复用 `new-api-tailscale` 的 Serve TCP 8765 配置，命令 `tailscale serve --bg --tcp=8765 tcp://192.168.0.118:8765`。独立于原有 HTTPS 443，不修改 New API 服务。
- 用户收藏 HTTPS 域名加原私密路径；域名根路径不公开数据，也不跳转到私密路径。日志不记录访问路径，禁止公开分享完整链接。
- ZIP 最大 8 GiB，代理关闭请求缓冲，避免先把整个包写到 LightSail 磁盘。

回滚：移走此单独 Nginx 配置，`nginx -t && systemctl reload nginx`；NAS 执行 `docker exec new-api-tailscale tailscale serve --tcp=8765 off`；删除此子域名的 DNS 记录即可。不要 reset Tailscale Serve，否则会影响原有 New API HTTPS 配置。软件与 NAS 本地数据不需要回滚。
