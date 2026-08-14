# 数据来源与边界

## 公开数据包

公开仓库的 `app/viewer-data.json` 由 `scripts/build_public_demo.py` 确定性生成。它只包含用于驱动界面的合成轨迹、合成 HUD 数字、合成发动机阶段和合成圆弧序列，不包含 Flight 13 观测，也不宣称拟合真实任务。

合成包保留与私有研究包相同的表结构，使服务器、绘图和交互逻辑可以公开测试。其 `distribution.profile` 为 `public_synthetic_demo`，`contains_flight_observations` 明确为 `false`。

当前 v1.5 合成包还包含由合成 ECEF 位置序列确定性计算的二阶差分字段 `ecef_ax_mps2`、`ecef_ay_mps2`、`ecef_az_mps2`。它们不是观测，也不是对 Flight 13 拟合结果的替代品。

## 私有冻结数据包

`scripts/build_viewer_data.py` 可从外部研究工作区读取十个输入，并在私有数据包中写入：

- 相对于研究工作区根目录的输入路径；
- 每个输入文件的 SHA-256；
- 表头、紧凑行数组和解释标记；
- 时间、坐标系与不可解释为物理真值的显式声明。

这类数据包含第三方轨迹和广播派生观测，默认不进入公开仓库。研究者应在自己有权使用的数据环境内生成和保管。

## 第三方轨迹

私有研究版的轨迹候选点来自 StarDash 对 SpaceX 公共直播遥测的第三方 public-feed 回放。公开仓库没有分发这些点，原因包括：

- 上游坐标基准、滤波和丢点机制没有独立文档；
- 它可能和视频 HUD 来自共同的遥测源；
- 密集轨迹是显示插值，不是新的位置观测；
- 绝对时间对齐仍含候选偏移和频道延迟混淆。

私有动力学质量反演可以读取条件重建轨迹的 ECEF 二阶导数；额定推力、气动、零风和发动机数量仍是外部或工程假设。公开包只用合成输入执行同一公式，页面显示的动力学质量与窗口端点质量差均不具有 Flight 13 数据含义。

## 视频与 HUD 图像

视频是本地运行资产，不进入 Git 历史。公开数据包不记录视频文件哈希或媒体元数据；运行时是否挂载本地视频以 `/health.json` 为准。

完整 HUD 原帧可在私有研究环境中由 `scripts/build_source_hud_archive.py` 打包到 `runtime/source-hud.zip`。ZIP 被 Git 忽略；公开仓库没有代表帧或其他广播截图。

## 第三方资产

HUD 三维载具几何来自 Clarence365 / Sketchfab，页面标注 CC BY 4.0。广播画面、商标、公开遥测和派生截图可能具有独立权利要求；代码仓库的许可证不能自动覆盖这些材料。

HUD 渲染固定使用仓库内 vendored Three.js r167；其 MIT 许可证保存在 `app/vendor/three/LICENSE`，避免页面运行依赖外部 CDN。
