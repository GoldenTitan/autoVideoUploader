import logging
# 基本配置，尽早进行，影响所有后续的 logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

import configparser
import os
import time # 用于调试时可能的暂停
from web import web_interaction,video_utils
from log_utils import setup_logger
import re # 导入re模块用于正则表达式提取数字
import shutil # 导入shutil模块用于文件移动

# 自定义异常
class LoginFailureException(Exception):
    """当网站登录失败时抛出此异常。"""
    pass

# 初始化日志
# 移除旧的 logger 初始化，因为 basicConfig 已经做了基础配置，
# setup_logger 将进一步添加 handlers。
# 我们需要确保 setup_logger 获取的是根 logger 或应用级 logger 来添加其 handlers
# 或者修改 setup_logger 使其能正确作用于已由 basicConfig 初始化的系统。

# 让我们先尝试直接调用 setup_logger 看它如何与 basicConfig 交互
# 注意：basicConfig 设置的 level 和 format 是针对根 logger 的默认 handler。
# setup_logger 可能会添加额外的 handlers。
logger = setup_logger( 
    __name__, # 或者尝试 logging.getLogger() 来获取根 logger，或者 "VideoUploaderProject"
    log_dir=os.path.join(os.path.dirname(__file__), "logs"),
    log_file="app.log",
    log_level=logging.INFO # 确保 setup_logger 内部的 handlers 也遵循此级别
)

def load_config(script_dir):
    """加载配置文件 config.ini"""
    config_path = os.path.join(script_dir, 'config', 'config.ini')
    if not os.path.exists(config_path):
        logger.error(f"配置文件 {config_path} 未找到!")
        raise FileNotFoundError(f"配置文件 {config_path} 未找到!")
    
    config = configparser.ConfigParser()
    try:
        # 以 UTF-8 编码读取配置文件，防止中文乱码
        with open(config_path, 'r', encoding='utf-8') as f:
            config.read_file(f)
    except UnicodeDecodeError as e:
        logger.error(f"读取配置文件 {config_path} 时发生编码错误 (尝试UTF-8失败): {e}")
        logger.error("请确保 config.ini 文件是以 UTF-8 编码保存的。")
        raise
    except Exception as e:
        logger.error(f"读取配置文件 {config_path} 时发生其他错误: {e}")
        raise
    return config

def get_videos_from_folder(video_folder, tracker_file_path, start_video_number=111):
    """
    获取指定文件夹下待上传的视频列表。
    会排除掉那些已经在 tracker_file_path 文件中记录过的视频。
    只包含文件名数字大于等于 start_video_number 的视频。
    视频按文件名中的数字排序。
    """
    uploaded_videos = set()
    if os.path.exists(tracker_file_path):
        with open(tracker_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                uploaded_videos.add(line.strip())
    
    videos_to_upload = []
    if not os.path.isdir(video_folder):
        logger.error(f"视频文件夹 {video_folder} 不存在或不是一个目录。")
        return videos_to_upload
        
    video_files = []
    for filename in os.listdir(video_folder):
        if filename.lower().endswith('.mp4'): # 只处理 .mp4 文件
            # 从文件名提取数字，例如 "海外猫咪视频大赏111.mp4" -> 111
            match = re.search(r'(\d+)', filename)
            if match:
                video_number = int(match.group(1))
                if video_number >= start_video_number:
                    video_path = os.path.join(video_folder, filename)
                    if video_path not in uploaded_videos:
                        video_files.append({'path': video_path, 'number': video_number, 'filename': filename})
                    else:
                        logger.info(f"视频 {filename} 已记录为上传过，将跳过。")
            else:
                logger.warning(f"无法从文件名 {filename} 中提取编号，将跳过。")

    # 按视频编号排序
    video_files.sort(key=lambda x: x['number'])
    
    # 提取排序后的路径列表
    videos_to_upload = [vf['path'] for vf in video_files]
    
    return videos_to_upload

def mark_as_uploaded(video_path, tracker_file_path):
    """将指定视频标记为已上传，追加其路径到记录文件。"""
    with open(tracker_file_path, 'a', encoding='utf-8') as f:
        f.write(f"{video_path}\n")

def main_upload_cycle(config, script_directory, videos_to_process_current_batch, tracker_file, move_files_config):
    """执行单次上传周期的核心逻辑。"""
    if not videos_to_process_current_batch:
        logger.info("当前批次没有视频可供上传。")
        return

    move_successful_enabled = move_files_config['enabled']
    archive_folder_path = move_files_config['archive_folder']
    move_failed_enabled = move_files_config.get('move_failed_enabled', False)
    failed_videos_folder_path = move_files_config.get('failed_videos_folder')

    # 确保存档文件夹存在 (用于成功上传的视频)
    if move_successful_enabled and archive_folder_path and not os.path.exists(archive_folder_path):
        try:
            os.makedirs(archive_folder_path)
            logger.info(f"已创建存档文件夹: {archive_folder_path}")
        except OSError as e:
            logger.error(f"创建存档文件夹 {archive_folder_path} 失败: {e}. 成功文件将不会被移动。")
            move_successful_enabled = False # 创建失败则禁用移动成功文件功能

    # 新增：确保失败视频文件夹存在
    if move_failed_enabled and failed_videos_folder_path and not os.path.exists(failed_videos_folder_path):
        try:
            os.makedirs(failed_videos_folder_path)
            logger.info(f"已创建失败视频文件夹: {failed_videos_folder_path}")
        except OSError as e:
            logger.error(f"创建失败视频文件夹 {failed_videos_folder_path} 失败: {e}. 失败文件将不会被移动。")
            move_failed_enabled = False # 创建失败则禁用移动失败文件功能

    for video_full_path in videos_to_process_current_batch:
        logger.info(f"******************************************************\n")
        logger.info(f"======== 开始处理视频: {video_full_path} ========")
        logger.info(f"******************************************************\n")
        driver = None
        upload_successful = False
        try:
            logger.debug(f"为视频 {os.path.basename(video_full_path)} 创建 WebDriver 实例...")
            driver = web_interaction.create_driver(config)
            if not driver:
                logger.error(f"无法为视频 {os.path.basename(video_full_path)} 创建 WebDriver 实例，跳过此视频。")
                mark_as_uploaded(video_full_path, tracker_file)
                logger.warning(f"视频 {video_full_path} 因WebDriver创建失败已记录到追踪文件，不会重试。")
            else:
                logger.debug(f"为视频 {os.path.basename(video_full_path)} 登录网站...")
                if not web_interaction.login_to_website(driver, config):
                    critical_error_msg = f"关键错误：为视频 {os.path.basename(video_full_path)} 登录网站失败。请检查 Cookies 或手动登录流程。程序将终止。"
                    logger.critical(critical_error_msg)
                    if driver:
                        driver.quit()
                    raise LoginFailureException(critical_error_msg)
            
                logger.debug(f"成功为视频 {os.path.basename(video_full_path)} 登录/导航到上传页面。")
                time.sleep(5)

                upload_successful = web_interaction.perform_video_upload(driver, video_full_path, '', None, config)
            
            mark_as_uploaded(video_full_path, tracker_file)
            
            if upload_successful:
                logger.info(f"视频 {video_full_path} 上传成功并已记录到追踪文件。")
                time.sleep(10) # 短暂等待，原逻辑保留

                # 将移动成功视频的逻辑块移到这里
                if move_successful_enabled and archive_folder_path:
                    try:
                        video_filename = os.path.basename(video_full_path)
                        destination_path = os.path.join(archive_folder_path, video_filename)
                        if os.path.exists(video_full_path): # 确保源文件存在才移动
                            shutil.move(video_full_path, destination_path)
                            logger.info(f"视频 {video_filename} 已成功移动到存档文件夹")
                        else:
                            logger.warning(f"尝试移动视频 {video_filename} 到存档文件夹，但源文件不存在。可能已被其他进程处理。")
                    except Exception as e:
                        logger.error(f"移动已上传视频 {video_full_path} 到存档文件夹失败: {e}")
            else: # upload_successful is False
                logger.error(f"视频 {video_full_path} 上传失败。该视频已记录到追踪文件，不会重试。")
                
                # 将移动失败视频的逻辑块移到这里
                if move_failed_enabled and failed_videos_folder_path:
                    try:
                        video_filename = os.path.basename(video_full_path)
                        destination_path = os.path.join(failed_videos_folder_path, video_filename)
                        if os.path.exists(video_full_path): # 确保源文件存在才移动
                            shutil.move(video_full_path, destination_path)
                            logger.info(f"上传失败的视频 {video_filename} 已移动到: {destination_path}")
                        else:
                            logger.warning(f"尝试移动失败视频 {video_filename} 到失败文件夹，但源文件不存在。")
                    except Exception as e:
                        logger.error(f"移动上传失败的视频 {video_full_path} 到失败文件夹失败: {e}")

        except LoginFailureException: # 单独捕获登录失败，以便向上抛出
            raise
        except Exception as e_outer: # 捕获处理单个视频时的其他意外错误
            logger.error(f"处理视频 {video_full_path} 过程中发生意外错误: {e_outer}", exc_info=True)
            # 发生意外错误时，也认为上传失败，并尝试移动（如果配置了）
            upload_successful = False # 确保标记为失败
            if not os.path.exists(tracker_file) or video_full_path not in open(tracker_file, 'r', encoding='utf-8').read():
                mark_as_uploaded(video_full_path, tracker_file) # 确保在意外错误时也标记，如果之前没标记的话
            if move_failed_enabled and failed_videos_folder_path:
                try:
                    video_filename = os.path.basename(video_full_path)
                    destination_path = os.path.join(failed_videos_folder_path, video_filename)
                    if os.path.exists(video_full_path):
                        shutil.move(video_full_path, destination_path)
                        logger.info(f"因意外错误导致上传失败的视频 {video_filename} 已移动到: {destination_path}")
                    else:
                        logger.warning(f"尝试移动因意外错误失败的视频 {video_filename} 到失败文件夹，但源文件不存在。")
                except Exception as e_move:
                    logger.error(f"移动因意外错误上传失败的视频 {video_full_path} 到失败文件夹失败: {e_move}")
        finally:
            if driver:
                logger.debug(f"正在关闭视频 {os.path.basename(video_full_path)} 的浏览器实例...")
                driver.quit()
                logger.debug(f"视频 {os.path.basename(video_full_path)} 的浏览器实例已关闭。")
            else:
                logger.debug(f"视频 {os.path.basename(video_full_path)} 的 WebDriver 实例未创建或已提前处理。")
            time.sleep(5)
        logger.info(f"******************************************************\n")
        logger.info(f"======== 完成处理视频: {video_full_path} ========\n")
        logger.info(f"******************************************************\n")
    logger.info("当前批次的视频均已尝试处理。")

def main():
    """主函数，执行整个视频上传流程，包含定时和数量控制。"""
    script_directory = os.path.dirname(__file__)

    try:
        config_parser = load_config(script_directory)
        video_source_folder = config_parser.get('General', 'video_source_folder')

        upload_interval_hours = config_parser.getint('General', 'upload_interval_hours', fallback=8)
        videos_per_batch = config_parser.getint('General', 'videos_per_batch', fallback=10)
        start_video_number_initial = config_parser.getint('General', 'start_video_number_initial', fallback=111)
        
        # 文件移动相关配置 (成功上传的视频)
        move_successful_files_enabled = config_parser.getboolean('General', 'move_uploaded_files', fallback=True)
        raw_archive_folder = config_parser.get('General', 'uploaded_archive_folder', fallback='UploadedArchive')
        
        # 新增：失败视频移动相关配置
        move_failed_files_enabled = config_parser.getboolean('General', 'move_failed_videos', fallback=False)
        raw_failed_videos_folder = config_parser.get('General', 'failed_videos_folder', fallback='FailedUploads')

        # 处理存档文件夹路径 (成功上传)
        if not os.path.isabs(raw_archive_folder):
            archive_folder = os.path.join(script_directory, raw_archive_folder)
        else:
            archive_folder = raw_archive_folder

        # 新增：处理失败视频文件夹路径
        if not os.path.isabs(raw_failed_videos_folder):
            failed_videos_folder = os.path.join(script_directory, raw_failed_videos_folder)
        else:
            failed_videos_folder = raw_failed_videos_folder

        move_files_settings = {
            'enabled': move_successful_files_enabled,
            'archive_folder': archive_folder if move_successful_files_enabled else None,
            'move_failed_enabled': move_failed_files_enabled,
            'failed_videos_folder': failed_videos_folder if move_failed_files_enabled else None
        }

        raw_tracker_path_config = config_parser.get('General', 'uploaded_tracker_file', fallback='uploaded_videos_tracker.txt')
        raw_tracker_path = raw_tracker_path_config.split('#')[0].strip()
        if not os.path.isabs(raw_tracker_path):
            tracker_file = os.path.join(script_directory, raw_tracker_path)
        else:
            tracker_file = raw_tracker_path
        
        logger.info(f"视频上传任务启动。源文件夹: {video_source_folder}, 追踪文件: {tracker_file}")
        if move_files_settings['enabled']:
            logger.info(f"成功上传的视频将被移动到: {move_files_settings['archive_folder']}")
        else:
            logger.info("成功上传的视频将不会被移动。")
        if move_files_settings['move_failed_enabled']:
            logger.info(f"上传失败的视频将被移动到: {move_files_settings['failed_videos_folder']}")
        else:
            logger.info("上传失败的视频将不会被移动。")
        logger.info(f"将每隔 {upload_interval_hours} 小时上传最多 {videos_per_batch} 个视频。")
        logger.info(f"首次将从文件名编号不小于 {start_video_number_initial} 的视频开始处理。")

        while True:
            logger.info(f"开始新一轮视频上传检查 (间隔: {upload_interval_hours} 小时, 批次数量: {videos_per_batch})...")
            
            all_potential_videos = get_videos_from_folder(video_source_folder, tracker_file, start_video_number_initial)
            
            if not all_potential_videos:
                logger.info("目前没有找到新的、符合条件的视频可供上传。")
            else:
                logger.info(f"找到 {len(all_potential_videos)} 个潜在待上传视频。")
                
                videos_for_this_run = all_potential_videos[:videos_per_batch]
                logger.info(f"本轮将尝试上传 {len(videos_for_this_run)} 个视频: {videos_for_this_run}")
                
                # 注意：main_upload_cycle 现在可能会抛出 LoginFailureException
                main_upload_cycle(config_parser, script_directory, videos_for_this_run, tracker_file, move_files_settings)
                
                if len(videos_for_this_run) < videos_per_batch:
                    logger.info(f"本轮上传数量 ({len(videos_for_this_run)}) 少于批次上限 ({videos_per_batch})，可能所有符合条件的视频都已处理完毕。")

            logger.info(f"本轮上传结束。将在 {upload_interval_hours} 小时后再次检查。")
            time.sleep(upload_interval_hours * 60 * 60)

    except FileNotFoundError as e:
        logger.error(f"初始化错误 (文件未找到): {e}")
    except configparser.Error as e:
        logger.error(f"读取配置文件错误: {e}")
    except LoginFailureException as e: # 捕获登录失败异常
        logger.critical(f"登录失败，程序终止: {e}") # 使用 critical 级别记录
        # 此处不需要显式退出，异常会使 while True 循环停止
    except Exception as e:
        logger.error(f"发生未预期错误: {e}", exc_info=True)

if __name__ == "__main__":
    main() # 程序入口 