# Flight 13 星箭反演查看器

一个用于讲解 Flight 13 视频证据反演方法的开源查看器。公开仓库只附带合成演示数据，不分发第三方轨迹、广播截图、HUD 原帧或视频；私有研究数据可在本地通过同一数据合同接入。项目重点是保留来源、口径和不确定性，不把显示候选量写成已经恢复的物理真值。

![公开演示版页面预览](docs/preview.png)

## 目录

```text
app/                 浏览器页面、合成演示数据包和 HUD 子查看器
src/flight13_viewer/ 无第三方运行依赖的本地 HTTP/Range 服务
scripts/             从研究工作区重建数据包和封装 HUD 帧
tests/               数据、UI、服务器合同测试
docs/                方法、来源、部署和清理记录
deploy/              systemd 与 nginx 示例
media/               本地视频挂载点；视频默认不进入 Git
runtime/             可选的 HUD 原帧 ZIP；默认不进入 Git
```

## 快速运行

需要 Python 3.11 或更新版本。页面必须通过 HTTP 服务打开，不能直接双击 `index.html`。

在 Windows 上，直接双击仓库根目录的 `start-viewer.cmd`。脚本会自动：

- 使用系统中的 `python`，不要求预先建立虚拟环境；
- 寻找 `media` 目录中的视频；
- 找不到本地视频时自动进入数据演示模式；
- 加载可选的 `runtime\source-hud.zip`，启动服务并打开浏览器。

只检查环境而不启动服务：

```powershell
.\start-viewer.cmd -Check
```

指定其他视频：

```powershell
.\start-viewer.cmd -VideoPath "D:\media\Flight13_web_720p.mp4"
```

也可以按标准 Python 包方式安装：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
flight13-viewer --video-path "D:\media\Flight13_web_720p.mp4"
```

没有视频时可检查数据和界面：

```powershell
flight13-viewer --allow-missing-video
```

随后访问 `http://127.0.0.1:8765/`。视频和完整 HUD 原帧都不是页面启动必需；公开仓库不携带它们。

普通 `pip install .` 构建的 wheel 会一并安装页面资产。若页面资产单独部署，可用 `--app-dir` 或环境变量 `FLIGHT13_VIEWER_APP_DIR` 指定其位置。

## 数据包

重建公开仓库内的纯合成演示数据：

```powershell
python scripts/build_public_demo.py
```

该命令只运行解析公式，不读取 Flight 13 视频、轨迹或 HUD 观测。

在私有研究工作区中，可另行生成完整冻结数据包：

研究工作区是外部输入，不复制进本仓库。它需要保留 `data_raw/` 与 `data_processed/flight13/` 的既有目录结构。

```powershell
python scripts/build_viewer_data.py --source-root "C:\path\to\research-workspace"
python scripts/build_source_hud_archive.py --source-root "C:\path\to\hud-assets"
```

`build_viewer_data.py` 生成 `app/viewer-data.json` 与确定性的 gzip 副本，并记录输入路径和 SHA-256；其输出包含第三方与广播派生观测，未经权利审查不应提交到公开仓库。`build_source_hud_archive.py` 生成被 Git 忽略的私有 `runtime/source-hud.zip`。

## 验证

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src scripts tests
```

## 质量模型

视频只提供每一级独立的无尺度圆弧指标 `q_B(t)` 与 `q_S(t)`。页面默认的吨位来自外部构型假设：`M0=4929 t`、一级起飞占比 `w_B=3611/4929`、一级图形归零保留质量 `D_B=311 t`、二级图形归零保留质量 `D_S=118 t`。

```text
P_B,0 = w_B M0 - D_B
P_S,0 = (1-w_B) M0 - D_S
M_B(t) = D_B + P_B,0 q_B(t)
M_S(t) = D_S + P_S,0 q_S(t)
```

这些输入把无尺度图形映射到吨位；不是视频独立反演出的绝对质量。完整说明见 [docs/METHODOLOGY.md](docs/METHODOLOGY.md)。

## Git 与公开发布

- 本项目原创代码与原创说明文档以 [MIT License](LICENSE.md) 发布，版权人为 `beibeifeng`。
- MIT 许可不覆盖第三方组件、轨迹数据、广播画面、HUD 图像、视频、商标或模型派生资产；各项边界见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
- MP4、完整 HUD 帧 ZIP、缓存、日志和虚拟环境不会进入普通 Git 历史。
- 若确实要版本化视频，`.gitattributes` 要求使用 Git LFS；仍应先确认版权与仓库额度。
- 当前公开版已用合成数据替换广播派生数据和第三方轨迹，且不包含广播截图。CC BY 4.0 模型派生几何按要求署名并说明修改。
- 已随仓库分发的第三方组件及归属见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
- GitHub Pages 只能托管静态页面，不能替代本项目所需的视频 Range 服务和可选 HUD 帧路由。生产部署见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。
