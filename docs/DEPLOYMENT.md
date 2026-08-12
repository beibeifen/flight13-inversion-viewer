# 部署

推荐拓扑：nginx 对外提供 HTTPS、静态文件和 MP4 Range；Python 服务监听回环地址，负责健康端点及可选 HUD ZIP 路由。

## 安装

```bash
python3 -m venv /opt/flight13-viewer/.venv
/opt/flight13-viewer/.venv/bin/pip install /opt/flight13-viewer
install -m 0644 Flight13_web_720p.mp4 /srv/flight13-viewer-media/
```

复制并调整 `deploy/flight13-viewer.service.example` 与 `deploy/nginx.conf.example`。启用前先执行：

```bash
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now flight13-viewer nginx
curl --fail http://127.0.0.1:8766/health.json
```

## 注意事项

- 对外优先使用 HTTPS；部分网络会干扰大体积明文视频传输。
- nginx 直接服务 MP4，保留 `Range`、`Accept-Ranges` 和 `sendfile`。
- `viewer-data.json` 可启用 gzip；不要 gzip MP4。
- 数据文件名若不版本化，应使用验证缓存或短缓存；更新后先核验内容哈希。
- 生产机只部署 `app/`、已安装 Python 包和运行资产，不需要复制研究工作区、缓存或构建输入。
