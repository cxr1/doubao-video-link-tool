# 短视频直链提取工具（GUI，Windows 可运行）

## 功能
- 输入豆包视频分享链接，自动提取 `share_id` 和 `video_id`
- 输入抖音视频链接，自动提取 `aweme_id`
- 调用豆包分享接口获取视频直链
- 自动识别豆包或抖音链接并提取直链
- 抖音链接默认先走分享页解析；识别到异常链接（如 `aweme/v1/play`、页面链接）时再自动回退到 `Playwright`
- 展示：
  - 主链接（`main`）
  - 备用链接（`backup`）
- 分辨率、提示词
- 一键复制主链接或备用链接
- 一键预览（默认浏览器打开视频链接）
- 一键下载为本地 MP4（带进度条）

## 运行环境
- Python 3.9+
- Windows / macOS / Linux（GUI 使用 Tkinter）

## 本地运行
```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python doubao_video_link_gui.py
```

> 说明：`playwright` 首次使用需要安装浏览器内核（上面的 `playwright install chromium`）。

## Windows 打包为 EXE
### 方法 1：一键脚本
直接双击运行：
```bat
build_windows.bat
```

### 方法 2：GitHub Actions（Mac 也能用）
仓库内已提供工作流：
`/.github/workflows/build-windows-exe.yml`

使用步骤：
1. 把项目推送到 GitHub 仓库
2. 打开 `Actions` 页签
3. 选择 `Build Windows EXE`
4. 点击 `Run workflow`
5. 运行完成后在 Artifacts 下载 `DoubaoVideoLinkTool-windows-exe`

### 方法 3：手动命令（在 Windows 上执行）
```bash
python -m pip install -r requirements.txt
python -m pip install pyinstaller
pyinstaller --onefile --windowed --name DoubaoVideoLinkTool doubao_video_link_gui.py
```

打包后可执行文件：
`dist\DoubaoVideoLinkTool.exe`

## 使用步骤
1. 粘贴豆包或抖音视频链接到「分享链接」输入框
2. 点击「获取视频直链」
3. 在结果区可选择：
   - 复制链接
   - 预览视频
   - 下载视频到本地

## 说明
- 工具基于豆包分享接口：`/creativity/share/get_video_share_info`
- 接口会返回 `play_info.main` 和 `play_info.backup`
- 某些网络环境下可能存在代理/证书问题，程序内置了多种重试策略（系统代理/直连、证书校验开关）
