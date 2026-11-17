# 部署

先完成 README 的数据初始化与可选检索索引，再选择进程管理和反向代理。

## Python 服务

`deploy/ziwei-agent.service` 是 systemd 示例，项目路径按实际安装位置替换。
该文件通过 uv 加载 `.env`；修改配置或后端后需重启服务。

```sh
sudo install -m 644 deploy/ziwei-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ziwei-agent
```

建议为自己的部署设置专用运行用户和文件权限。模板的代理网段对应当前 Docker 网络，应根据实际 Nginx 地址调整，不能直接信任公网传入的转发头。

## Nginx 与 HTTPS

当前线上实例使用 `compose.yaml` 中的 Nginx 转发到宿主机应用；其中保留的 agent 容器不是本地快速开始入口。不要直接启动整个生产 Compose 文件。

`deploy/nginx/conf.d/` 中的域名、证书路径和后端地址都需要按自己的部署修改。首次申请证书前先使用 HTTP 配置，保留 `/.well-known/acme-challenge/` 的 webroot，申请成功后再启用 TLS；直接使用 HTTPS 配置而没有证书会导致 Nginx 启动失败。

当前体验站的证书维护方式见 [DOMAIN.md](../deploy/DOMAIN.md)。`renew-certificates.sh` 与 systemd 定时器可复用，安装路径需同步修改。

## 容器镜像

Dockerfile 可构建应用镜像；前端静态文件和 SQL 一并复制。镜像不包含凭据和业务数据。启动前从仓库运行 SQL 初始化，将数据库与检索服务连接通过环境变量传入。

```sh
docker build -t ziwei-agent .
docker run --rm --env-file .env -p 127.0.0.1:8000:8000 ziwei-agent
```

容器里的 `127.0.0.1` 指向容器本身，请使用从容器可达的数据库地址。
