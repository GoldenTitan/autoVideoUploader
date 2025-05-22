# 自动视频上传项目 (VideoUploaderProject)

## 概述

本项目是一个 Python 脚本，旨在自动化将本地视频文件上传到指定网站（例如头条创作平台）的过程。它通过 Selenium 控制 Microsoft Edge 浏览器来模拟用户操作，包括登录、选择视频文件、处理封面以及发布视频。脚本被设计为可配置、可定时执行，并能批量处理视频。

## 主要功能

-   **配置文件驱动**: 大部分行为通过 `VideoUploaderProject/config/config.ini` 文件进行配置。
-   **智能视频扫描与筛选**:
    -   直接扫描指定的视频源文件夹。
    -   根据文件名中的数字编号（如 "海外猫咪视频大赏111.mp4"）进行排序和筛选。
    -   可配置从指定的视频编号开始处理。
-   **定时执行与批量上传**:
    -   可配置每隔N小时自动执行上传任务。
    -   可配置每次任务上传固定数量的视频。
-   **自动 WebDriver管理**: 自动检测已安装的 Edge 浏览器版本，并下载/管理兼容的 Edge WebDriver。
-   **Cookie 持久化与登录校验**:
    -   支持保存和加载登录 Cookies，以减少手动登录的频率。
    -   若Cookie登录失败，会发出严重警告并终止程序，防止无效操作。
-   **灵活的封面选择**: 支持通过截取视频帧的方式自动选择封面。
-   **上传跟踪与文件管理**:
    -   记录已尝试上传（无论成功或失败）的视频到追踪文件（默认为 `uploaded_videos_tracker.txt`），避免重复处理。
    -   (可选) 成功上传的视频会自动移动到指定的存档文件夹，保持源文件夹整洁。
-   **日志记录与轮转**:
    -   详细记录操作过程和错误信息到日志文件 (`VideoUploaderProject/logs/app.log`)。
    -   日志文件每日自动轮转，并保留最近7天的日志备份，防止日志文件过大。
    -   在特定错误发生时保存浏览器截图。
-   **手动登录支持**: 如果 Cookie 失效或首次运行，脚本会等待用户手动登录。
-   **可配置浏览器行为**: 支持无头模式、自定义 User-Agent、窗口大小等。

## 先决条件

1.  **Python 3.7+**
2.  **Microsoft Edge 浏览器**: 需要已安装在您的系统上。
3.  **依赖库**:
    *   `selenium`
    *   `requests`
    您可以通过 `requirements.txt` 文件安装这些依赖。

## 安装与配置

1.  **获取项目文件**:
    确保您拥有项目的所有文件。

2.  **安装依赖**:
    在项目根目录下打开终端或命令行，运行以下命令来安装必要的 Python 库：
    ```bash
    pip install -r requirements.txt
    ```

3.  **配置文件**:
    主要的配置文件位于 `VideoUploaderProject/config/config.ini`。请根据您的实际情况修改此文件。

    关键配置项说明：

    *   **`[General]`**:
        *   `video_source_folder`: 存放原始视频文件的文件夹路径。视频文件应遵循命名规则，如 "海外猫咪视频大赏xxx.mp4"，其中 "xxx" 为数字编号。
        *   `uploaded_tracker_file`: 记录已尝试上传视频信息的文件路径。默认为 `uploaded_videos_tracker.txt`。
        *   `edgedriver_path`: (可选) Edge WebDriver (`msedgedriver.exe`) 的路径。脚本会尝试自动管理。
        *   `edge_browser_path`: (可选) Microsoft Edge 浏览器主程序 (`msedge.exe`) 的路径。通常脚本会自动查找。
        *   `cookies_file_path`: 保存浏览器登录 Cookies 的 JSON 文件路径。默认为项目根目录下的 `browser_cookies.json`。
        *   `upload_interval_hours`: 每隔多少小时执行一次上传任务。默认为 `8`。
        *   `videos_per_batch`: 每次任务上传多少个视频。默认为 `10`。
        *   `start_video_number_initial`: 从文件名编号大于等于哪个数字的视频开始处理。这主要影响首次运行或追踪文件被清空后的起始点。默认为 `111`。
        *   `move_uploaded_files`: 是否将成功上传的视频移动到存档文件夹 (`true` 或 `false`)。默认为 `true`。
        *   `uploaded_archive_folder`: 成功上传的视频存放的存档文件夹路径。如果路径是相对的，则是相对于 `VideoUploaderProject` 目录。默认为 `UploadedArchive`。
        *   `video_list_file`: (已废弃，不再由主程序使用) 原用于记录待上传视频文件名的文本文件路径。

    *   **`[WebTarget]`**:
        *   `upload_url`: 目标网站的视频上传页面 URL。
        *   `cookie_domain_url`: 加载/保存 Cookies 时需要访问的域名 URL (通常是主站域名)。

    *   **`[BrowserSettings]`**:
        *   `headless`: 是否以无头模式运行浏览器 (`true` 或 `false`)。无头模式下浏览器界面不可见。
        *   `user_agent`: 自定义浏览器的 User-Agent 字符串 (可选)。
        *   `window_size`: 浏览器窗口大小，格式为 `宽度,高度` (例如 `1920,1080`)。在非无头模式下生效。
        *   `edge_profile_path`: Edge 浏览器用户数据目录的路径 (可选, 用于加载特定浏览器配置)。
        *   `manual_login_wait_timeout_seconds`: 等待用户手动登录的超时时间（秒）。

4.  **准备视频文件**:
    将你的视频文件（例如，"海外猫咪视频大赏111.mp4", "海外猫咪视频大赏112.mp4" 等）放入 `config.ini` 中 `video_source_folder` 指定的文件夹内。脚本会根据文件名中的数字自动排序和筛选。

## 使用方法

1.  确保所有配置（尤其是 `config.ini`）已正确设置。
2.  在项目根目录下打开终端或命令行。
3.  运行主脚本：
    ```bash
    python VideoUploaderProject/main.py
    ```
4.  脚本将开始执行：
    *   扫描视频源文件夹，根据配置筛选和排序待处理视频。
    *   启动 Edge 浏览器。
    *   尝试使用 Cookies 自动登录。如果失败，程序将记录严重错误并终止。如果 Cookies 无效或首次运行，会提示并等待用户手动登录。
    *   按计划（例如，每8小时上传10个视频）处理视频：
        *   上传视频文件。
        *   自动选择封面（通过截取）。
        *   点击发布。
        *   视频处理完毕后（无论成功或失败）会被记录到追踪文件。
        *   如果成功上传且配置了移动文件，视频会被移到存档文件夹。
    *   所有操作都会详细记录在可轮转的日志文件中。

## 文件结构简述

```
removePython/
│
├── VideoUploaderProject/
│   ├── main.py                 # 主执行脚本
│   ├── log_utils.py            # 日志工具配置模块
│   ├── config/
│   │   └── config.ini          # 配置文件
│   ├── web/
│   │   ├── __init__.py
│   │   ├── web_interaction.py  # Selenium 浏览器交互逻辑
│   │   ├── video_utils.py      # (可能存在的)视频处理工具类
│   │   └── logs/               # 浏览器交互相关的截图日志 (Selenium截图用)
│   └── logs/
│       └── app.log             # 应用主日志文件 (每日轮转)
│
├── rename_videos.py            # (可选的)视频重命名脚本
├── requirements.txt            # Python 依赖库
└── README.md                   # 本文件
```
*(根据实际情况，`video_utils.py` 可能不存在或有其他用途)*

## 日志与截图

-   **主日志**: `VideoUploaderProject/logs/app.log` 记录了脚本运行的详细信息和错误。此日志文件每日会自动轮转，旧日志会带有日期后缀（如 `app.log.YYYY-MM-DD`），并保留最近7天的备份。
-   **截图**: 在 Selenium 操作过程中发生特定错误时（如元素找不到、超时等），脚本会自动截取当前浏览器屏幕并保存到 `VideoUploaderProject/web/logs/` 目录下，以便于调试。

## 注意事项与故障排查

-   **视频文件命名**: 为确保正确筛选和排序，视频文件应遵循包含数字编号的命名模式，如 `海外猫咪视频大赏111.mp4`。程序会提取文件名中的数字部分。
-   **XPath 依赖**: 脚本中的许多自动化操作依赖于目标网站前端页面的 XPath 表达式。如果网站结构发生变化，这些 XPath 可能失效，导致脚本运行失败。届时需要更新 `VideoUploaderProject/web/web_interaction.py` 中的相关 XPath。
-   **WebDriver 版本**: 虽然脚本会尝试自动管理 WebDriver，但如果遇到问题，请确保 `msedgedriver.exe` 与您的 Edge 浏览器版本兼容。
-   **网络问题**: 确保脚本运行时网络连接稳定。
-   **首次运行与登录**: 首次运行或 Cookie 失效时，需要用户在自动打开的浏览器窗口中手动完成登录操作。请留意控制台的提示信息。
-   **配置文件路径**: 配置文件中的路径（如 `video_source_folder`, `uploaded_archive_folder`）如果是相对路径，请注意其相对的基准点（通常是 `VideoUploaderProject` 目录或脚本执行的当前工作目录，具体见代码实现）。推荐使用绝对路径以避免混淆。 