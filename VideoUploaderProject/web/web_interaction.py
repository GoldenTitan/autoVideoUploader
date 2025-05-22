from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService # Import Edge Service
from selenium.webdriver.edge.options import Options as EdgeOptions # Import Edge Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
import time
import os
import subprocess
import re
import platform as py_platform
import requests # Dependency: pip install requests
import zipfile
import io
from selenium.common.exceptions import WebDriverException, SessionNotCreatedException, TimeoutException
import json # Added for cookie handling
import shutil # For shutil.which

# Windows-specific import for browser version detection
if py_platform.system() == "Windows":
    try:
        import winreg
    except ImportError:
        logging.warning("winreg module not found. Needed for automatic Edge browser version detection from registry.")
        winreg = None # type: ignore

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Cookie Handling Constants and Functions ---
COOKIE_FILE_PATH_CONFIG_KEY = 'cookies_file_path'
DEFAULT_COOKIE_FILE_NAME = "browser_cookies.json"
LOGS_DIR_NAME = "logs" # For screenshots

def _ensure_logs_dir(base_script_path=__file__):
    """Ensures the logs directory exists relative to the script or project."""
    try:

        script_dir = os.path.dirname(os.path.abspath(base_script_path))
        logs_path = os.path.join(script_dir, LOGS_DIR_NAME)
        if not os.path.exists(logs_path):
            os.makedirs(logs_path)
            logger.debug(f"日志目录已创建: {logs_path}")
        return logs_path
    except Exception as e:
        logger.error(f"创建日志目录失败: {e}")
        return os.path.join(os.path.dirname(os.path.abspath(base_script_path)), LOGS_DIR_NAME) # Return path anyway

def _get_cookie_file_path(config):
    script_dir = os.path.dirname(os.path.abspath(__file__))

    project_root_candidate = os.path.dirname(script_dir) 
    
    cookie_file_name_from_config = config.get('General', COOKIE_FILE_PATH_CONFIG_KEY, fallback=DEFAULT_COOKIE_FILE_NAME)
    
    if os.path.isabs(cookie_file_name_from_config):
        return cookie_file_name_from_config
    else:

        return os.path.join(project_root_candidate, cookie_file_name_from_config)


def save_cookies(driver, config):
    cookie_file = _get_cookie_file_path(config)
    try:
        cookies = driver.get_cookies()
        cookie_dir = os.path.dirname(cookie_file)
        if not os.path.exists(cookie_dir) and cookie_dir: # If cookie_dir is not empty (not current dir)
            os.makedirs(cookie_dir, exist_ok=True)
            logger.debug(f"为 Cookies 文件创建目录: {cookie_dir}")

        with open(cookie_file, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=4)
        logger.info(f"浏览器 Cookies 已保存到: {cookie_file}")
    except Exception as e:
        logger.error(f"保存 Cookies 失败: {e}", exc_info=True)

def load_cookies_on_domain(driver, config, domain_url):
    cookie_file = _get_cookie_file_path(config)
    if not os.path.exists(cookie_file):
        logger.info(f"Cookies 文件未找到 ({cookie_file})，将不加载 Cookies。")
        return False

    try:
        logger.debug(f"为加载 Cookies，准备导航到域: {domain_url}")
        driver.get(domain_url)
        # time.sleep(1) # Allow page to settle, might be needed if redirects are quick

        with open(cookie_file, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        
        for cookie in cookies:
            # Minimal validation for essential keys
            if 'name' in cookie and 'value' in cookie:
                # Selenium can be picky about 'expiry'. If it's float, convert to int.
                if 'expiry' in cookie and isinstance(cookie['expiry'], float):
                    cookie['expiry'] = int(cookie['expiry'])

                try:
                    driver.add_cookie(cookie)
                except Exception as e_add_cookie:
                    logger.warning(f"添加单个 Cookie 失败: {cookie.get('name', 'N/A')}. 错误: {e_add_cookie}. Cookie 数据: {cookie}")
            else:
                logger.warning(f"跳过格式不正确的 Cookie: {cookie}")

        logger.debug(f"Cookies 已从 {cookie_file} 加载并尝试添加到域 {domain_url}。")
        # driver.refresh() # Refresh page to apply cookies, optional
        # time.sleep(1) # Wait for refresh
        return True
    except Exception as e:
        logger.error(f"加载或添加 Cookies 失败 (域: {domain_url}): {e}", exc_info=True)
        return False

# --- End Cookie Handling ---


# Helper functions for Edge and WebDriver management

def _get_edge_browser_version_windows():
    """
    Tries to get the installed Microsoft Edge browser version on Windows.
    Checks registry keys and common installation paths.
    """
    if not winreg:
        logger.warning("winreg 模块未找到，跳过注册表检查 Edge 版本。")
    else:
        registry_keys = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Edge\BLBeacon", "version"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{56EB18F8-B008-461B-9D5D-D886E684E904}", "pv"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{56EB18F8-B008-461B-9D5D-D886E684E904}", "pv")
        ]
        for root, path, value_name in registry_keys:
            try:
                key = winreg.OpenKey(root, path)
                version, _ = winreg.QueryValueEx(key, value_name)
                winreg.CloseKey(key)
                if version:
                    logger.debug(f"从注册表获取 Edge 浏览器版本 ('{path}\\\\{value_name}'): {version}")
                    return str(version)
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.debug(f"读取注册表键 '{path}\\\\{value_name}' 时出错: {e}")
                continue
    
    edge_exe_paths = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft\Edge\Application\msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft\Edge\Application\msedge.exe")
    ]
    for edge_path in edge_exe_paths:
        if os.path.exists(edge_path):
            try:
                result = subprocess.run([edge_path, "--version"], capture_output=True, text=True, check=True, encoding='utf-8')
                version_output = result.stdout.strip()
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", version_output)
                if match:
                    version = match.group(1)
                    logger.debug(f"通过命令获取 Edge 浏览器版本 ('{edge_path} --version'): {version}")
                    return version
            except Exception as e:
                logger.debug(f"通过命令 '{edge_path} --version' 获取 Edge 版本时出错: {e}")
                continue
                
    logger.warning("无法在 Windows 上自动确定 Edge 浏览器版本。")
    return None

def _get_local_webdriver_version(driver_executable_path):
    """
    获取本地 WebDriver 可执行文件的版本。
    """
    if not os.path.exists(driver_executable_path):
        logger.debug(f"WebDriver 可执行文件未找到: {driver_executable_path}")
        return None
    try:
        process = subprocess.run([driver_executable_path, "--version"], capture_output=True, text=True, check=False, timeout=5, encoding='utf-8')
        output = process.stdout.strip()
        match = re.search(r"Microsoft Edge WebDriver (\d+\.\d+\.\d+\.\d+)", output)
        if match:
            version = match.group(1)
            logger.debug(f"找到本地 WebDriver '{driver_executable_path}' 版本: {version}")
            return version
        else:
            logger.warning(f"无法从 '{driver_executable_path}' 的输出中解析 WebDriver 版本: {output}")
            return None
    except subprocess.TimeoutExpired:
        logger.error(f"从 '{driver_executable_path}' 获取 WebDriver 版本超时。它可能已损坏或无响应。")
        return None
    except Exception as e:
        logger.error(f"从 '{driver_executable_path}' 获取 WebDriver 版本时出错: {e}")
        return None

def _get_webdriver_download_url(browser_major_version, os_platform_suffix="win64"):
    """
    尝试确定 Edge WebDriver 的下载 URL。
    使用 Microsoft 的 LATEST_RELEASE_{MAJOR_VERSION} 端点。
    """
    logger.debug(f"尝试查找与 Edge 主版本 {browser_major_version} ({os_platform_suffix}) 兼容的 WebDriver 下载 URL")
    base_url = "https://msedgedriver.azureedge.net"
    
    try:
        version_info_url = f"{base_url}/LATEST_RELEASE_{browser_major_version}"
        if py_platform.system() == "Windows":
            version_info_url = f"{base_url}/LATEST_RELEASE_{browser_major_version}_WINDOWS"
        elif py_platform.system() == "Linux":
             version_info_url = f"{base_url}/LATEST_RELEASE_{browser_major_version}_LINUX"
        elif py_platform.system() == "Darwin":
             version_info_url = f"{base_url}/LATEST_RELEASE_{browser_major_version}_MACOS"

        response = requests.get(version_info_url, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('content-type', '').lower()
        if 'utf-16' in content_type:
            driver_version_full = response.content.decode('utf-16-le', errors='ignore').strip('\x00').strip()
        else:
            driver_version_full = response.text.strip()
        
        if not re.match(r"^\d+\.\d+\.\d+\.\d+$", driver_version_full):
            logger.warning(f"从 '{version_info_url}' 获取的版本字符串 '{driver_version_full}' 不是有效的版本格式。")
            stable_url = f"{base_url}/LATEST_STABLE"
            response_stable = requests.get(stable_url, timeout=10)
            response_stable.raise_for_status()
            stable_content_type = response_stable.headers.get('content-type', '').lower()
            if 'utf-16' in stable_content_type:
                 stable_version = response_stable.content.decode('utf-16-le', errors='ignore').strip('\x00').strip()
            else:
                 stable_version = response_stable.text.strip()

            if stable_version.startswith(str(browser_major_version) + "."):
                logger.debug(f"使用 LATEST_STABLE 版本 {stable_version}，因为它匹配主版本 {browser_major_version}。")
                driver_version_full = stable_version
            else:
                logger.error(f"无法使用 LATEST_RELEASE 或 LATEST_STABLE 确定 Edge {browser_major_version} 的合适 WebDriver 版本字符串。")
                return None
        
        logger.info(f"确定 Edge {browser_major_version} 的 WebDriver 版本为: {driver_version_full}")
        return f"{base_url}/{driver_version_full}/edgedriver_{os_platform_suffix}.zip"
        
    except requests.exceptions.RequestException as e:
        logger.error(f"从 Azure 获取 Edge {browser_major_version} 的 WebDriver 版本/URL 时出错: {e}")
        return None

def _download_and_extract_webdriver(webdriver_url, driver_target_path):
    """
    从 URL 下载 WebDriver 并将 msedgedriver.exe 解压缩到 driver_target_path。
    显示中文下载进度。
    """
    driver_dir = os.path.dirname(driver_target_path)
    os.makedirs(driver_dir, exist_ok=True) # 确保目录存在

    if os.path.exists(driver_target_path):
        try:
            logger.debug(f"发现已存在的 WebDriver: {driver_target_path}，尝试删除...")
            os.remove(driver_target_path)
            logger.debug(f"已删除旧的 WebDriver: {driver_target_path}")
        except OSError as e:
            logger.error(f"删除旧的 WebDriver {driver_target_path} 失败: {e}. 请手动删除并重试。")
            return False # 返回 False 表示准备失败
    
    try:
        logger.info(f"开始下载 WebDriver 从: {webdriver_url}")
        response = requests.get(webdriver_url, stream=True, timeout=300) # 5分钟超时
        response.raise_for_status()
        
        total_size = response.headers.get('content-length')
        if total_size is None:
            logger.warning("无法获取文件总大小，将不显示下载进度。")
            file_content = response.content
        else:
            total_size = int(total_size)
            downloaded_size = 0
            file_content_buffer = io.BytesIO()
            chunk_size = 8192 
            last_reported_progress = -1

            logger.info(f"文件总大小: {total_size / (1024*1024):.2f} MB")
            for data_chunk in response.iter_content(chunk_size=chunk_size):
                file_content_buffer.write(data_chunk)
                downloaded_size += len(data_chunk)
                progress_percentage = int((downloaded_size / total_size) * 100)
                
                if progress_percentage != last_reported_progress:
                    print(f"下载进度: {progress_percentage}% ({downloaded_size / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB)", end='\r')
                    last_reported_progress = progress_percentage
            print() 
            file_content = file_content_buffer.getvalue()
            logger.info("WebDriver 下载完成。")

        with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
            driver_filename_in_zip = None
            for member_name in zf.namelist():
                if member_name.lower().endswith("msedgedriver.exe"):
                    driver_filename_in_zip = member_name
                    break
            
            if not driver_filename_in_zip:
                logger.error(f"在从 {webdriver_url} 下载的 zip 文件中未找到 'msedgedriver.exe'。")
                return False

            with zf.open(driver_filename_in_zip) as source, open(driver_target_path, "wb") as target_file:
                target_file.write(source.read())
            
            if py_platform.system() != "Windows":
                os.chmod(driver_target_path, 0o755)
            
            logger.info(f"WebDriver '{driver_filename_in_zip}' 已解压缩到 '{driver_target_path}'")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"下载 WebDriver 失败 (URL: {webdriver_url}): {e}")
        return False
    except zipfile.BadZipFile:
        logger.error(f"下载的文件不是一个有效的 ZIP 文件 (URL: {webdriver_url}).")
        return False
    except Exception as e:
        logger.error(f"下载或解压 WebDriver 时发生错误: {e}", exc_info=True)
        return False

def _ensure_compatible_edgedriver(config):
    """
    检查是否存在兼容的 Edge WebDriver，如果需要则下载它。
    返回兼容 WebDriver 的路径，如果设置失败则返回 None。
    """
    browser_version_str = None
    if py_platform.system() == "Windows":
        browser_version_str = _get_edge_browser_version_windows()
    else:
        logger.warning(f"{py_platform.system()} 上的 Edge 浏览器版本自动检测未完全实现。请确保 Edge 已安装并通过 PATH 或配置可访问。")
        try:
            edge_exe = config.get('General', 'edge_browser_path', fallback='msedge') # Use 'msedge' as generic command
            # For Linux, it might be 'microsoft-edge-stable' or similar
            if py_platform.system() == "Linux" and not shutil.which(edge_exe):
                 edge_exe_alternatives = ['microsoft-edge-stable', 'microsoft-edge-beta', 'microsoft-edge-dev']
                 for alt_exe in edge_exe_alternatives:
                     if shutil.which(alt_exe):
                         edge_exe = alt_exe
                         break
            
            result = subprocess.run([edge_exe, "--version"], capture_output=True, text=True, check=True, encoding='utf-8')
            version_output = result.stdout.strip()
            # Example: Microsoft Edge 123.4567.89.0 or just 123.4567.89.0
            match = re.search(r"(\d+\.\d+\.\d+\.\d+)", version_output)
            if match: browser_version_str = match.group(1)
        except Exception as e:
            logger.debug(f"在 {py_platform.system()} 上通过命令获取 Edge 版本时出错: {e}")


    if not browser_version_str:
        logger.error("无法确定 Edge 浏览器版本。无法确保 WebDriver 兼容。")
        return None

    try:
        browser_major_version = browser_version_str.split('.')[0]
    except Exception as e:
        logger.error(f"无法从浏览器版本字符串 '{browser_version_str}' 解析主版本: {e}")
        return None

    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_driver_name = "msedgedriver.exe"
    # Default candidate path is next to this script
    default_driver_path_candidate = os.path.join(script_dir, default_driver_name) 
    
    webdriver_path_from_config = config.get('General', 'edgedriver_path', fallback=default_driver_path_candidate)
    
    if not os.path.isabs(webdriver_path_from_config):
        # If relative, assume it's relative to this script's directory.
        final_webdriver_path = os.path.normpath(os.path.join(script_dir, webdriver_path_from_config))
    else:
        final_webdriver_path = os.path.normpath(webdriver_path_from_config)
    
    webdriver_dir = os.path.dirname(final_webdriver_path)
    if not os.path.exists(webdriver_dir) and webdriver_dir :
        try:
            os.makedirs(webdriver_dir, exist_ok=True)
            logger.info(f"已创建 WebDriver 目录: {webdriver_dir}")
        except Exception as e:
            logger.error(f"创建 WebDriver 目录 {webdriver_dir} 失败: {e}")
            return None
            
    logger.debug(f"期望的 WebDriver 路径: {final_webdriver_path}")

    local_webdriver_version_str = _get_local_webdriver_version(final_webdriver_path)
    needs_download = True
    if local_webdriver_version_str:
        try:
            local_webdriver_major_version = local_webdriver_version_str.split('.')[0]
            if local_webdriver_major_version == browser_major_version:
                logger.debug(f"在 '{final_webdriver_path}' 找到兼容的本地 WebDriver 版本 {local_webdriver_version_str} (适用于 Edge {browser_major_version})。")
                needs_download = False
            else:
                logger.warning(f"本地 WebDriver 版本 {local_webdriver_version_str} (主版本 {local_webdriver_major_version}) "
                               f"与 Edge 版本 {browser_version_str} (主版本 {browser_major_version}) 不兼容。")
        except Exception as e:
            logger.warning(f"无法从本地 WebDriver 版本 '{local_webdriver_version_str}' 解析主版本: {e}。假设不兼容。")
    else:
        logger.info(f"在 '{final_webdriver_path}' 未找到本地 WebDriver 或无法确定其版本。")

    if needs_download:
        logger.info(f"尝试下载 Edge 主版本 {browser_major_version} 的 WebDriver。")
        
        os_platform_tag = ""
        system = py_platform.system()
        arch = py_platform.architecture()[0] # '64bit' or '32bit'
        machine = py_platform.machine().lower() # e.g., 'amd64', 'x86_64', 'arm64'

        if system == "Windows":
            os_platform_tag = "win64" if arch == '64bit' else "win32"
        elif system == "Linux":
            # Assume 64-bit for Linux, which is most common for WebDriver releases
            os_platform_tag = "linux64" 
        elif system == "Darwin": # macOS
            # Check machine type for Apple Silicon (ARM) vs Intel
            os_platform_tag = "mac_arm64" if "arm" in machine or machine == "aarch64" else "mac64"
        else:
            logger.error(f"不支持的操作系统平台进行 WebDriver 下载: {system}")
            return None

        webdriver_url = _get_webdriver_download_url(browser_major_version, os_platform_tag)
        
        if not webdriver_url:
            logger.error(f"无法自动确定 Edge {browser_major_version} ({os_platform_tag}) 的 WebDriver 下载 URL。")
            logger.error(f"请检查网络连接或手动将 Edge {browser_major_version} 的 '{default_driver_name}' 下载到 '{final_webdriver_path}'。")
            return None

        if _download_and_extract_webdriver(webdriver_url, final_webdriver_path):
            logger.info(f"WebDriver 已成功下载并解压缩到 '{final_webdriver_path}'。")
            new_webdriver_version = _get_local_webdriver_version(final_webdriver_path)
            if new_webdriver_version and new_webdriver_version.startswith(browser_major_version + "."):
                logger.info(f"已成功设置兼容的 WebDriver 版本 {new_webdriver_version}。")
                return final_webdriver_path
            else:
                logger.error(f"下载的 WebDriver 版本 ({new_webdriver_version}) 仍然与 Edge {browser_major_version} 不兼容或无法验证。")
                return None
        else:
            logger.error(f"从 {webdriver_url} 下载和设置 WebDriver 失败。")
            return None
            
    return final_webdriver_path


def create_driver(config):
    """创建并返回一个 Edge WebDriver 实例，在创建前检查并准备WebDriver"""
    
    compatible_webdriver_path = _ensure_compatible_edgedriver(config)
    if not compatible_webdriver_path:
        logger.error("未能确保兼容的 Edge WebDriver。中止驱动程序创建。")
        return None
    
    if not os.path.exists(compatible_webdriver_path):
        logger.error(f"兼容的 WebDriver 路径 '{compatible_webdriver_path}' 在设置尝试后仍不存在。")
        return None

    edge_binary_to_use = None
    configured_edge_path = config.get('General', 'edge_browser_path', fallback=None)

    if configured_edge_path and os.path.exists(configured_edge_path):
        edge_binary_to_use = configured_edge_path
        logger.info(f"使用配置文件中的 Edge 浏览器二进制文件: {edge_binary_to_use}")
    elif py_platform.system() == "Windows":
        default_paths = [
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft\Edge\Application\msedge.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft\Edge\Application\msedge.exe")
        ]
        for p in default_paths:
            if os.path.exists(p):
                edge_binary_to_use = p
                logger.debug(f"在默认位置找到 Edge 浏览器二进制文件: {edge_binary_to_use}")
                break
    else: 
        # For non-Windows, rely on shutil.which (PATH) or explicit config
        # Common command names for Edge on Linux/Mac
        edge_commands = ['msedge', 'microsoft-edge', 'microsoft-edge-stable', 'microsoft-edge-beta', 'microsoft-edge-dev']
        for cmd in edge_commands:
            found_in_path = shutil.which(cmd)
            if found_in_path:
                edge_binary_to_use = found_in_path
                logger.info(f"在 PATH 中找到 Edge 浏览器二进制文件: {edge_binary_to_use} (使用命令 '{cmd}')")
                break
        if not edge_binary_to_use and configured_edge_path: 
             logger.warning(f"配置文件中的 Edge 浏览器路径 '{configured_edge_path}' 未找到或无效。")


    if not edge_binary_to_use:
        logger.error("未找到 Microsoft Edge 浏览器可执行文件。请检查安装、PATH 或 config.ini 中的 'edge_browser_path'。")
        return None
    
    logger.info("尝试创建 Edge WebDriver 实例...")
    try:
        edge_options = EdgeOptions()
        edge_options.binary_location = edge_binary_to_use

        # Common options for robustness and to appear more like a normal browser
        # edge_options.add_argument("--start-maximized") # 移除全屏启动参数
        edge_options.add_argument("--disable-gpu") # Often helpful, especially in headless or virtual environments
        edge_options.add_argument("--no-sandbox") # Can be necessary in some environments like Docker or CI
        edge_options.add_argument("--disable-dev-shm-usage") # Overcomes limited resource problems in Docker/Linux
        edge_options.add_argument("ignore-certificate-errors") # Useful for sites with self-signed certs (use with caution)
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"]) # Reduce "controlled by automation" bar and some logs
        edge_options.add_argument('--disable-blink-features=AutomationControlled') # Another attempt to hide automation

        headless_mode = config.getboolean('BrowserSettings', 'headless', fallback=False)
        user_agent = config.get('BrowserSettings', 'user_agent', fallback=None)
        window_size = config.get('BrowserSettings', 'window_size', fallback=None)
        profile_path_config = config.get('BrowserSettings', 'edge_profile_path', fallback=None)

        if headless_mode:
            logger.info("以无头模式启动 Edge。")
            edge_options.add_argument("--headless=new") # Modern headless
        if user_agent:
            logger.info(f"设置 User-Agent: {user_agent}")
            edge_options.add_argument(f"user-agent={user_agent}")
        if window_size and not headless_mode: # Window size is not applicable in headless=new
            logger.info(f"设置窗口大小: {window_size}")
            edge_options.add_argument(f"--window-size={window_size}")
        
        if profile_path_config:
            if not os.path.isabs(profile_path_config):
                script_dir_abs = os.path.dirname(os.path.abspath(__file__))
                # Assume profile_path_config is relative to project root (parent of script_dir)
                project_root_abs = os.path.dirname(script_dir_abs)
                profile_path_abs = os.path.normpath(os.path.join(project_root_abs, profile_path_config))
            else:
                profile_path_abs = os.path.normpath(profile_path_config)
            
            if os.path.exists(profile_path_abs):
                 logger.info(f"使用 Edge 用户数据目录: {profile_path_abs}")
                 edge_options.add_argument(f"user-data-dir={profile_path_abs}")
                 # profile_directory_name = config.get('BrowserSettings', 'edge_profile_directory', fallback=None)
                 # if profile_directory_name:
                 #    edge_options.add_argument(f"profile-directory={profile_directory_name}")
            else:
                logger.warning(f"Edge 用户数据目录 '{profile_path_abs}' (来自 '{profile_path_config}') 未找到。将使用默认配置文件。")
        
        # Disable password manager popups (might not be needed if using profile)
        prefs = {"credentials_enable_service": False, "profile.password_manager_enabled": False}
        edge_options.add_experimental_option("prefs", prefs)
        
        edge_service = EdgeService(executable_path=compatible_webdriver_path)
        
        logger.debug(f"使用服务初始化 WebDriver: {compatible_webdriver_path}")

        driver = webdriver.Edge(service=edge_service, options=edge_options)
        logger.info("Edge WebDriver 实例创建成功。")
        return driver
        
    except SessionNotCreatedException as e:
        logger.error(f"SessionNotCreatedException: 创建 Edge WebDriver 会话失败。这通常意味着 Edge 版本和 WebDriver 版本不兼容（尽管已检查）。错误: {e}", exc_info=True)
        logger.error("请仔细检查您的 Edge 浏览器版本，并确保有匹配的 WebDriver 可用。")
        logger.error(f"当前 Edge 二进制文件: {edge_binary_to_use}")
        logger.error(f"使用的 WebDriver: {compatible_webdriver_path} (版本: {_get_local_webdriver_version(compatible_webdriver_path)})")
        return None
    except WebDriverException as e:
        logger.error(f"WebDriverException: 创建 Edge WebDriver 时发生错误。错误: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Edge WebDriver 创建期间发生意外错误: {e}", exc_info=True)
        return None

def login_to_website(driver, config):
    """处理网站登录逻辑。如果需要，等待用户手动登录，并保存/加载cookies。"""
    upload_url = config.get('WebTarget', 'upload_url')
    cookie_domain_url = config.get('WebTarget', 'cookie_domain_url', fallback="https://mp.toutiao.com") 
    logs_path = _ensure_logs_dir()

    # 尝试加载 Cookies
    cookies_loaded_successfully = load_cookies_on_domain(driver, config, cookie_domain_url)
    if cookies_loaded_successfully:
        logger.info("已尝试加载 Cookies。现在导航到上传页面。")
    else:
        logger.info("未加载 Cookies 或加载失败。")
    
    logger.debug(f"导航到上传页面: {upload_url}")
    driver.get(upload_url)
    time.sleep(3) # 给页面加载或重定向留出时间

    # 页面上目标元素的定位符 (例如，视频上传区域)
    # **** 这是关键，需要根据实际页面进行调整 ****
    target_page_element_locator = (By.CLASS_NAME, "byte-upload-trigger-area") 

    # 登录页面指示元素的定位符列表 (示例，需要根据实际登录页面调整)
    login_page_indicators = [
        (By.XPATH, "//input[@type='text' and contains(@placeholder, '手机号')]"), 
        (By.XPATH, "//input[@type='password']"),
        (By.XPATH, "//*[contains(text(),'短信登录') or contains(text(),'验证码登录')]"),
        (By.XPATH, "//*[contains(text(),'密码登录')]"),
        (By.XPATH, "//*[contains(text(),'扫码登录')]"),
        (By.CSS_SELECTOR, ".login-button"), # 通用登录按钮
        (By.CSS_SELECTOR, "div.qrcode"),    # 二维码区域
        # 检查URL是否是已知的登录/SSO域
        lambda d: "login" in d.current_url.lower() or "sso" in d.current_url.lower() or "passport" in d.current_url.lower()
    ]

    try:
        # 尝试直接查找目标页面元素，看是否已登录且在正确页面
        WebDriverWait(driver, 10).until(EC.presence_of_element_located(target_page_element_locator))
        logger.debug(f"成功导航到上传页面并找到目标元素 '{target_page_element_locator[1]}'。假定已登录。")
        
        # 如果之前未保存过cookies，或者加载失败了但现在成功了（可能通过浏览器profile登录），则保存当前cookies
        cookie_file = _get_cookie_file_path(config)
        if not os.path.exists(cookie_file) or not cookies_loaded_successfully:
             logger.debug("之前未保存或加载 Cookies，现在保存当前 Cookies 以备将来使用。")
             save_cookies(driver, config)
        return True
    except TimeoutException:
        logger.info(f"直接访问上传页面后未立即找到目标元素 '{target_page_element_locator[1]}'。检查是否在登录页面。")
        
        is_on_login_page = False
        for indicator in login_page_indicators:
            try:
                if callable(indicator): # Lambda for URL check
                    if indicator(driver):
                        is_on_login_page = True
                        logger.debug(f"通过 URL '{driver.current_url}' 检测到可能在登录页面。")
                        break
                elif driver.find_elements(indicator[0], indicator[1]):
                    is_on_login_page = True
                    logger.debug(f"检测到登录页面元素: {indicator}。")
                    break
            except: #忽略查找元素时可能发生的任何错误
                pass # Continue waiting
                
        if is_on_login_page:
            logger.warning("检测到登录页面。请在自动化浏览器窗口中手动登录。")
            logger.debug(f"脚本将等待您登录，直到在页面 '{upload_url}' 上看到元素 '{target_page_element_locator[1]}'。")
            
            manual_login_timeout = config.getint('BrowserSettings', 'manual_login_wait_timeout_seconds', fallback=300)
            start_time = time.time()
            logged_in_successfully_manually = False
            
            while time.time() - start_time < manual_login_timeout:
                try:
                    # 检查当前URL是否是上传页面URL (或其一部分，以防参数变化)
                    # 并且目标元素已出现
                    if upload_url in driver.current_url and WebDriverWait(driver, 3).until(EC.presence_of_element_located(target_page_element_locator)):
                        logger.info(f"手动登录成功！已在页面 '{driver.current_url}' 检测到目标元素 '{target_page_element_locator[1]}'。")
                        logged_in_successfully_manually = True
                        break
                    else:
                        # 如果URL还不是上传URL，但也不是明确的登录URL了，也可能是登录后的中间页
                        current_url_lower = driver.current_url.lower()
                        if not ("login" in current_url_lower or "sso" in current_url_lower or "passport" in current_url_lower):
                            # 尝试重新导航到上传页，看是否已登录
                            logger.debug(f"当前 URL ({driver.current_url}) 不是登录页，尝试重新导航到上传页以确认登录状态。")
                            driver.get(upload_url) # Re-navigate
                            time.sleep(2)
                            # And check again for the target element immediately
                            if upload_url in driver.current_url and WebDriverWait(driver, 3).until(EC.presence_of_element_located(target_page_element_locator)):
                                logger.info(f"手动登录成功！重新导航后，在页面 '{driver.current_url}' 检测到目标元素。")
                                logged_in_successfully_manually = True
                                break
                except Exception: # TimeoutException or other
                    pass # Continue waiting
                
                logger.info(f"等待用户手动登录... 剩余时间: {int(manual_login_timeout - (time.time() - start_time))} 秒。当前 URL: {driver.current_url}")
                time.sleep(10) # 每10秒检查一次

            if logged_in_successfully_manually:
                logger.info("手动登录流程完成。保存当前 Cookies。")
                save_cookies(driver, config)
                return True
            else:
                logger.error(f"在 {manual_login_timeout} 秒内未检测到成功的手动登录或目标元素未出现。")
                try:
                    screenshot_path = os.path.join(logs_path, "manual_login_timeout.png")
                    driver.save_screenshot(screenshot_path)
                    logger.debug(f"已保存截图到: {screenshot_path}")
                except Exception as scr_e:
                    logger.error(f"保存截图失败: {scr_e}")
                return False
        else:
            logger.error(f"页面 ({driver.current_url}) 未识别为登录页面，但目标元素 '{target_page_element_locator[1]}' 也未找到。请检查页面状态和元素定位符。")
            try:
                screenshot_path = os.path.join(logs_path, "target_element_not_found_not_login_page.png")
                driver.save_screenshot(screenshot_path)
                logger.debug(f"已保存截图到: {screenshot_path}")
            except Exception as scr_e:
                logger.error(f"保存截图失败: {scr_e}")
            return False


def perform_video_upload(driver, video_file_path, video_title, cover_image_path, config):
    """在已登录的页面上执行视频上传操作"""
    logs_path = _ensure_logs_dir()
    try:
        logger.info(f"开始上传视频文件: {video_file_path}")

        xpath_strategy_2_input_general_hidden = "//input[@type='file' and (contains(@style,'display: none') or contains(@class,'hidden') or not(@visible)) and (@accept='video/*' or contains(@accept, '.mp4'))]" # 通用隐藏视频输入

        file_input_element = None
        
        # --- 尝试定位文件输入元素 (直接使用策略 2b) --- 
        logger.debug(f"尝试使用通用隐藏视频输入 XPath: '{xpath_strategy_2_input_general_hidden}'")
        try:

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath_strategy_2_input_general_hidden))
            )
            possible_inputs = driver.find_elements(By.XPATH, xpath_strategy_2_input_general_hidden)
            if possible_inputs:
                file_input_element = possible_inputs[0] # 取第一个匹配的
                logger.debug(f"成功: 找到一个或多个通用隐藏视频输入，选用第一个 ({xpath_strategy_2_input_general_hidden})。")

            else:
                logger.warning(f"失败: 未找到匹配 '{xpath_strategy_2_input_general_hidden}' 的元素，即使 presence_of_element_located 成功。")
        except TimeoutException:
            logger.warning(f"失败: 在10秒内未能通过 XPath '{xpath_strategy_2_input_general_hidden}' 找到任何元素。截图保存中...")
            screenshot_path = os.path.join(logs_path, "file_input_strategy2b_fail.png")
            driver.save_screenshot(screenshot_path)
            logger.debug(f"截图已保存到: {screenshot_path}")
        except Exception as e_gen_xpath:
            logger.warning(f"执行 XPath '{xpath_strategy_2_input_general_hidden}' 时发生意外错误: {e_gen_xpath}")
            screenshot_path = os.path.join(logs_path, "file_input_strategy2b_exception.png")
            driver.save_screenshot(screenshot_path)
            logger.debug(f"截图已保存到: {screenshot_path}")

        if not file_input_element:
            logger.error("所有定位策略均失败，未能找到文件输入元素。请检查上传页面的HTML结构和截图，并调整XPath选择器。")
            # 最终截图
            screenshot_path = os.path.join(logs_path, "file_input_all_strategies_failed.png")
            driver.save_screenshot(screenshot_path)
            logger.debug(f"最终截图已保存到: {screenshot_path}")
            return False

        # --- 文件路径发送 --- 
        logger.debug(f"文件输入元素已定位 ({file_input_element.tag_name}, id: {file_input_element.get_attribute('id')}, class: {file_input_element.get_attribute('class')})。发送文件路径: {os.path.abspath(video_file_path)}")
        try:

            file_input_element.send_keys(os.path.abspath(video_file_path))
            logger.debug("文件路径已成功发送到输入框。")
        except Exception as e_sendkeys:
            logger.error(f"向文件输入框直接发送路径失败: {e_sendkeys}")
            logger.debug("请检查截图，确认元素是否真的可以直接接收 send_keys，或是否需要JS辅助使其可见/可交互。")
            screenshot_path = os.path.join(logs_path, "send_keys_to_file_input_failed.png")
            driver.save_screenshot(screenshot_path)
            logger.debug(f"截图已保存到: {screenshot_path}")

            return False

        logger.debug("等待视频信息加载和表单出现……")
        
        try: # 主 TRY 块，用于文件选择后的视频处理步骤
            
            # --- 开始新的封面选择逻辑 ---
            logger.debug("开始选择封面...") 
            try: # 专门用于封面选择步骤的内部 try 块
                initial_cover_area_xpath = "/html/body/div[1]/div/div[3]/section/main/div[2]/div/div/div[2]/div/div/div/div[2]/div/div[1]/div/div/div/div[3]/div/div[2]/div[1]/div[2]/div[2]/div[2]/div[1]/div/div/div"
                capture_cover_tab_xpath = "/html/body/div[6]/div/div[2]/div/div[1]/ul/li[1]"
                next_step_button_xpath = "/html/body/div[6]/div/div[2]/div/div[2]/div"
                cover_confirm_op_xpath = "/html/body/div[6]/div/div[2]/div/div[1]/div/div[2]/div[2]/div[3]/div[3]/button[2]"
                final_confirm_op_xpath = "/html/body/div[7]/div/div[2]/div/div[2]/button[2]"

                logger.debug(f"尝试点击初始封面区域: {initial_cover_area_xpath}")
                initial_cover_area = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, initial_cover_area_xpath))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", initial_cover_area)
                time.sleep(0.5) # 点击前短暂暂停
                initial_cover_area.click()
                logger.debug("初始封面区域已点击。等待封面选项对话框...")
                time.sleep(2) # 等待对话框出现

                logger.debug(f"点击 '截取封面' 标签: {capture_cover_tab_xpath}")
                capture_tab = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, capture_cover_tab_xpath))
                )
                capture_tab.click()
                logger.debug("'截取封面' 标签已点击。")
                time.sleep(1) # 等待标签内容加载

                logger.debug(f"点击 '下一步' 按钮: {next_step_button_xpath}")
                next_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, next_step_button_xpath))
                )
                next_button.click()
                logger.debug("'下一步' 按钮已点击。")
                time.sleep(1) # 等待对话框内下一步操作

                logger.debug(f"点击 '确认' 按钮: {cover_confirm_op_xpath}")
                confirm_button = WebDriverWait(driver, 30).until(
                    EC.element_to_be_clickable((By.XPATH, cover_confirm_op_xpath))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", confirm_button)
                time.sleep(0.5) # 点击前短暂暂停
                confirm_button.click()
                logger.debug("封面选择 '确认' 按钮已点击。")
                time.sleep(2) # 如旧代码中一样，确认后等待处理

                # --- 修改后的最终确认按钮逻辑 ---
                logger.debug(f"检查并尝试点击封面编辑后的最终确认按钮: {final_confirm_op_xpath}")
                try:
                    # 首先，用短超时检查元素是否存在，避免长时间等待一个不存在的元素
                    WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, final_confirm_op_xpath))
                    )
                    logger.debug(f"最终确认按钮 (XPath: {final_confirm_op_xpath}) 存在。现在等待其可点击并尝试点击...")
                    
                    # 按钮存在，现在等待它可被点击（可能需要更长时间）
                    final_confirm_button_element = WebDriverWait(driver, 15).until(
                        EC.element_to_be_clickable((By.XPATH, final_confirm_op_xpath))
                    )
                    final_confirm_button_element.click()
                    logger.debug("封面最终确认按钮已成功点击。") # 使用 info 级别表示成功完成一个可选/条件步骤
                except TimeoutException:
                    logger.warning(f"封面最终确认按钮 (XPath: {final_confirm_op_xpath}) 未在预期时间内找到或变为可点击。此步骤可能为可选或页面行为已改变，将跳过。")
                    return False# 表示上传失败
                # --- 结束修改后的最终确认按钮逻辑 ---
                
                logger.info("封面截取与确认流程完成。")

            except TimeoutException as e_cover:
                logger.error(f"封面截取/确认过程中发生超时: {e_cover}")
                screenshot_path = os.path.join(logs_path, "cover_selection_timeout_error.png")
                driver.save_screenshot(screenshot_path)
                logger.debug(f"已保存封面选择超时截图到: {screenshot_path}")
                logger.error("封面截取/确认超时，已关闭浏览器窗口，标记该视频上传失败。")
                driver.quit()
                return False# 表示上传失败
            except Exception as e_cover_generic:
                logger.error(f"封面截取/确认过程中发生意外错误: {e_cover_generic}", exc_info=True)
                screenshot_path = os.path.join(logs_path, "cover_selection_unexpected_error.png")
                driver.save_screenshot(screenshot_path)
                logger.debug(f"已保存封面选择意外错误截图到: {screenshot_path}")
                return False # 表示上传失败
            # --- 结束新的封面选择逻辑 ---

            logger.debug("封面处理完成。") # 移除了日志中关于等待后点击发布的部分
            time.sleep(2) # 保留用户要求的在封面操作后的2秒等待

            text_indicator_xpath = "/html/body/div[1]/div/div[3]/section/main/div[2]/div/div/div[2]/div/div/div/div[2]/div/div[1]/div/div/div/div[3]/div/div[2]/div[1]/div[2]/div[2]/div[2]/div[2]"
            logger.debug(f"等待指定区域出现文本内容 (XPath: {text_indicator_xpath}) 以准备发布...")
            try:
                WebDriverWait(driver, 60).until( # 等待最多60秒
                    lambda d: d.find_element(By.XPATH, text_indicator_xpath).text.strip() != ""
                )
                logger.debug(f"指定区域 (XPath: {text_indicator_xpath}) 已出现文本内容。继续发布流程。")
            except TimeoutException:
                logger.error(f"在指定区域 (XPath: {text_indicator_xpath}) 等待文本内容超时（60秒）。视频可能未成功处理或状态未更新。截图保存中...")
                screenshot_path = os.path.join(logs_path, "text_appearance_timeout_for_publish.png")
                try:
                    driver.save_screenshot(screenshot_path)
                    logger.debug(f"截图已保存到: {screenshot_path}")
                except Exception as scr_e:
                    logger.error(f"保存截图失败: {scr_e}")
                return False # 表示上传失败，无法继续发布

            submit_button_locator = (By.XPATH, "//button[contains(.,'发布') and not(@disabled)]")
            logger.debug(f"尝试定位并点击发布按钮 ({submit_button_locator[1]})...")

            logger.debug("等待可能的遮罩层消失...")
            try:
                WebDriverWait(driver, 45).until( # 等待最多45秒让遮罩消失
                    EC.invisibility_of_element_located((By.XPATH, "//div[@class='mask ']"))
                )
                logger.debug("遮罩层已消失或超时。")
            except TimeoutException:
                logger.warning("等待遮罩层消失超时，但仍将尝试点击发布按钮。这可能会失败。截图保存中...")
                screenshot_path = os.path.join(logs_path, "mask_still_present_timeout.png")
                try:
                    driver.save_screenshot(screenshot_path)
                    logger.debug(f"截图已保存到: {screenshot_path}")
                except Exception as scr_e:
                    logger.error(f"保存截图失败: {scr_e}")
            
            # 再次确保按钮是可点击的，因为遮罩消失后，按钮状态可能再次变化
            logger.debug("重新确认发布按钮可点击性...")
            submit_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(submit_button_locator))

            submit_button.click() # 点击发布按钮
            logger.debug("发布按钮已点击。")

            # --- 开始处理可能的弹窗 ---
            try:
                logger.debug("检查是否存在需要额外确认的弹窗...")
                # 等待弹窗中的特定按钮出现，设置一个较短的超时时间，例如5秒
                popup_button_xpath = "/html/body/div[7]/div[2]/div/div[2]/div[3]/button[1]/span"
                popup_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, popup_button_xpath))
                )
                logger.debug("检测到弹窗，正在点击弹窗中的确认按钮...")
                popup_button.click()
                logger.debug("弹窗确认按钮已点击。")
                
                # 重新等待并点击发布按钮
                logger.debug("再次尝试点击发布按钮...")
                submit_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(submit_button_locator))
                submit_button.click()
                logger.debug("发布按钮已再次点击。")
                
            except TimeoutException:
                # 如果超时，说明弹窗没有出现，或者弹窗结构不是预期的，记录日志并继续
                logger.debug("未检测到需要额外确认的弹窗，或弹窗按钮未在预期时间内出现。")
            except Exception as e_popup:
                # 处理点击弹窗按钮时可能发生的其他异常
                logger.error(f"处理弹窗时发生意外错误: {e_popup}", exc_info=True)
                # 视情况决定是否需要返回False或抛出异常
            # --- 结束处理可能的弹窗 ---

            logger.debug("视频提交步骤已执行。请在浏览器中监控实际上传进度和最终状态。")
            logger.debug("程序将在此暂停一段时间以便您观察。")

        except TimeoutException as e_wait_title: # 这个 except 对应主 TRY 块
            logger.error(f"在视频处理或发布准备阶段发生超时: {e_wait_title}", exc_info=True)
            screenshot_path = os.path.join(logs_path, "after_file_selection_error.png")
            driver.save_screenshot(screenshot_path)
            logger.debug(f"已保存截图到: {screenshot_path}")
            return False

        logger.info("视频上传流程（到点击发布按钮）初步完成。")
        return True

    except Exception as e:
        logger.error(f"视频上传过程中发生未预期错误: {e}", exc_info=True)
        screenshot_path = os.path.join(logs_path, "perform_video_upload_unexpected_error.png")
        try:
            driver.save_screenshot(screenshot_path)
            logger.debug(f"已保存截图到: {screenshot_path}")
        except Exception as scr_e:
            logger.error(f"保存截图失败: {scr_e}")
        return False
