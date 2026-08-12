# 公开发布审计

审计日期：2026-08-12。

## 已排除

- Flight 13 视频与任何视频代理；
- 完整 HUD 原帧 ZIP；
- 六张广播代表帧；
- StarDash public-feed 原始定位点及其重建轨迹；
- 广播 HUD 数字转录、圆弧像素、图标读数与逐帧派生数据；
- 私有数据的输入 SHA-256、本机绝对路径、服务器地址、账号、密码、令牌和密钥；
- 缓存、日志、虚拟环境与构建产物。

## 已替换

- `app/viewer-data.json` 与 gzip 副本由 `scripts/build_public_demo.py` 生成，只包含合成演示量；
- 无本地视频时启动器自动进入数据演示模式；
- HUD 子查看器不再请求广播代表帧或逐秒视觉线索文件。

## 保留的第三方内容

- Three.js r167：MIT，许可证保存在 `app/vendor/three/LICENSE`；
- Clarence365 / Sketchfab 模型派生几何：CC BY 4.0，已署名、链接原始来源和许可证，并说明简化与浏览器适配修改。

## 许可范围

原创代码与原创说明文档使用 MIT License，版权人为 `beibeifeng`。MIT 不覆盖用户自行挂载的视频、HUD 原帧、商标或其他第三方材料。
