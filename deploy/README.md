# 外网入口

- Cloudflare：`sleep.ztmdsbt.site` A → `18.136.138.12`，仅 DNS，避免代理上传上限影响 ZIP。
- LightSail SSH：`sgrelay`；Nginx 配置 `/etc/nginx/conf.d/sleep.ztmdsbt.site.conf`。
- HTTPS：Let's Encrypt webroot `/var/lib/letsencrypt`；复用现有 certbot renew 定时任务和 reload-nginx hook。
- 回源：LightSail → Tailscale `100.120.30.7:8765` → NAS `192.168.0.118:8765`。
- NAS：复用 `new-api-tailscale` 的 Serve TCP 8765 配置，命令 `tailscale serve --bg --tcp=8765 tcp://192.168.0.118:8765`。独立于原有 HTTPS 443，不修改 New API 服务。
- 公网入口为 `https://sleep.ztmdsbt.site/`，独立 oauth2-breath-view 服务（127.0.0.1:4181）要求 GitHub 登录，仅允许 stofancy。会话使用独立 __Host-breath_view Cookie 和密钥，复用既有 GitHub OAuth 客户端。原私密链接跳转到根入口，仍必须登录。
- NAS capability 仅存在服务器上的 breath-view-upstream.conf，不能提交 Git；局域网访问方式不变。
- ZIP 最大 8 GiB，代理关闭请求缓冲，避免先把整个包写到 LightSail 磁盘。

回滚：移走此单独 Nginx 配置，`nginx -t && systemctl reload nginx`；NAS 执行 `docker exec new-api-tailscale tailscale serve --tcp=8765 off`；删除此子域名的 DNS 记录即可。不要 reset Tailscale Serve，否则会影响原有 New API HTTPS 配置。软件与 NAS 本地数据不需要回滚。

GitHub OAuth 应用 `New API Console`（3825816）必须登记两个精确 Redirect URI：`https://console.ztmdsbt.site/oauth2/callback` 和 `https://sleep.ztmdsbt.site/oauth2/callback`，均不启用通配匹配。仅测试未登录的 GitHub /login 页面不能验证回调匹配；必须完成实际登录并返回息览。
