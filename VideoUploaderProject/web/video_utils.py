import os
import subprocess
import logging
from datetime import datetime



def extract_cover_image(video_path, config, output_folder="VideoUploaderProject/temp_covers"):
    """使用 FFmpeg 从指定的视频文件中提取特定帧作为封面图片。"""
    # 从配置中获取要提取的帧的索引，如果未设置则默认为第 9 帧
    frame_index = config.getint('VideoSettings', 'cover_frame_index', fallback=9)
    # 从配置中获取 FFmpeg 可执行文件的路径，如果未设置则默认为 'ffmpeg' (假设在系统PATH中)
    ffmpeg_executable = config.get('General', 'ffmpeg_path', fallback='ffmpeg')

    if not os.path.exists(video_path): # 检查视频文件是否存在
        logging.error(f"视频文件不存在: {video_path}")
        return None # 如果视频文件不存在，记录错误并返回 None

    if not os.path.exists(output_folder): # 检查输出文件夹是否存在
        os.makedirs(output_folder) # 如果不存在，则创建该文件夹
        logging.info(f"创建临时封面文件夹: {output_folder}")

    # 从视频路径中提取文件名（不含扩展名）
    video_filename = os.path.splitext(os.path.basename(video_path))[0]
    # 构建封面图片的名称
    cover_image_name = f"{video_filename}_cover_frame_{frame_index}.jpg"
    # 构建封面图片的完整输出路径
    cover_image_path = os.path.join(output_folder, cover_image_name)

    # 构建 FFmpeg 命令列表
    command = [
        ffmpeg_executable,       # FFmpeg 程序路径
        '-i', video_path,        # 输入视频文件
        '-vf', f"select='eq(n,{frame_index})'", # 视频滤镜：选择等于指定帧号(n)的帧
        '-vframes', '1',        # 只输出 1 帧
        cover_image_path,      # 输出封面图片的路径
        '-y'                     # 如果输出文件已存在，则覆盖它
    ]

    try:
        logging.info(f"执行 FFmpeg 命令: {' '.join(command)}") # 记录将要执行的命令
        # 执行 FFmpeg 命令，捕获输出，进行文本解码，并检查是否有错误
        process = subprocess.run(command, capture_output=True, text=True, check=True, shell=False)
        logging.info(f"FFmpeg 输出: {process.stdout}") # 记录 FFmpeg 的标准输出
        if process.stderr:
            # FFmpeg 可能会将一些信息性内容输出到 stderr，所以这里作为 info 级别记录
            logging.info(f"FFmpeg 错误输出 (可能只是信息): {process.stderr}")
        logging.info(f"封面成功提取到: {cover_image_path}")
        return cover_image_path # 返回成功提取的封面图片路径
    except subprocess.CalledProcessError as e: # 如果 FFmpeg 执行返回非零退出码
        logging.error(f"FFmpeg 执行失败. 返回码: {e.returncode}")
        logging.error(f"FFmpeg stdout: {e.stdout}")
        logging.error(f"FFmpeg stderr: {e.stderr}")
        return None # 记录详细错误信息并返回 None
    except FileNotFoundError: # 如果 FFmpeg 可执行文件未找到
        logging.error(f"FFmpeg 命令 '{ffmpeg_executable}' 未找到。请确保它已安装并配置在系统PATH中，或在 config.ini 中正确指定了路径。")
        return None # 记录错误并返回 None

