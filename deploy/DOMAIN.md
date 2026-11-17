# 域名与 HTTPS

2026-11-17 已为 `lovelxr.site`、`www.lovelxr.site` 启用 HTTPS。HTTP 使用 308 保留路径、查询参数和请求方法跳转到 HTTPS；
80 端口保留 ACME 验证路径供自动续期使用。

## 当前部署

应用由宿主机 `ziwei-agent.service` 运行，Nginx 由 Docker Compose 运行。
实际配置为 `deploy/nginx/conf.d/ziwei.conf`，共享反向代理配置为
`agent-proxy.inc`，转发到宿主机 `172.18.0.1:8000`。保留 SSE 不缓冲设置。
不要执行 `docker compose up` 启动旧应用容器；只操作 Nginx 和 Certbot。

应用通过 `--proxy-headers --forwarded-allow-ips=127.0.0.1,172.18.0.0/16`
识别可信 Docker 网段传来的 HTTPS 协议，使登录 Cookie 正确带上 Secure。
Docker 网络变更后需要同步检查该网段和反向代理的宿主机地址。

证书来自 Let's Encrypt，通过 Certbot webroot 验证两个域名，无需停服。
证书及 ACME 账号位于 `deploy/certbot/conf/`，挑战目录为
`deploy/certbot/www/`，均已加入 `.gitignore`。不得提交或公开私钥。
首次证书有效期至 2027-02-15，后续以实际续期后的证书为准。
当前 ACME 账号未登记邮箱，续期情况通过 systemd 日志检查。

## 检查与重载

在 `/home/ziwei-agent` 执行：

```sh
docker compose exec -T nginx nginx -t
docker compose exec -T nginx nginx -s reload
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' https://lovelxr.site/
curl --noproxy '*' -sS -D - -o /dev/null http://lovelxr.site/
openssl x509 -in deploy/certbot/conf/live/lovelxr.site/fullchain.pem -noout -dates -ext subjectAltName
```

不要用 HTTP 配置覆盖当前 HTTPS 配置。

## 自动续期

`ziwei-certbot.timer` 每天在服务器时间 03:00 和 15:00 之后随机一小时内
检查续期，错过的任务会在下次开机补执行。续期脚本通过文件锁避免并发执行，
成功后检查 Nginx 配置并平滑重载。

```sh
systemctl list-timers ziwei-certbot.timer --no-pager
journalctl -u ziwei-certbot.service --no-pager -n 100
systemctl start ziwei-certbot.service
# 验证挑战和续期流程，不替换线上证书：
bash deploy/renew-certificates.sh --dry-run
```

定时器安装文件为 `deploy/ziwei-certbot.service` 和 `deploy/ziwei-certbot.timer`。
搬迁服务器时需复制证书目录并安装、启用这两个 unit，同时开放 80、443 端口。
Certbot 用法参考[官方文档](https://eff-certbot.readthedocs.io/en/stable/using.html#webroot)。
