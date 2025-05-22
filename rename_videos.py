import os

def batch_rename_videos(folder_path, base_name, start_number, extension):
    """
    批量重命名指定文件夹中的视频文件。

    参数:
    folder_path (str): 视频文件所在的文件夹路径。
    base_name (str): 新文件名的基本名称 (例如 "海外猫咪视频大赏")。
    start_number (int): 重命名的起始编号。
    extension (str): 视频文件的扩展名 (例如 ".mp4")。
    """
    print(f"开始处理文件夹: {folder_path}")
    print(f"新文件名基础: {base_name}")
    print(f"起始编号: {start_number:03d}")
    print(f"文件扩展名: {extension}")

    current_number = start_number
    files_renamed_count = 0

    try:
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(extension.lower()):
                old_file_path = os.path.join(folder_path, filename)
                
                # 生成新的文件名，确保编号是三位数，不足补零
                new_filename = f"{base_name}{current_number:03d}{extension}"
                new_file_path = os.path.join(folder_path, new_filename)

                # 检查新文件名是否已存在，以避免覆盖
                if os.path.exists(new_file_path):
                    print(f"警告: 文件 {new_filename} 已存在，跳过 {filename}")
                    # 可以选择是否因为新文件名已存在而递增 current_number
                    # 如果希望即使跳过也消耗一个编号，可以取消下一行的注释
                    # current_number += 1 
                    continue

                try:
                    os.rename(old_file_path, new_file_path)
                    print(f"已重命名: '{filename}' -> '{new_filename}'")
                    files_renamed_count += 1
                    current_number += 1
                except OSError as e:
                    print(f"错误: 重命名 '{filename}' 失败。原因: {e}")
            
    except FileNotFoundError:
        print(f"错误: 文件夹 '{folder_path}' 未找到。")
        return
    except Exception as e:
        print(f"发生未知错误: {e}")
        return

    print(f"\n处理完成。总共重命名了 {files_renamed_count} 个文件。")

if __name__ == "__main__":
    # ----- 请根据您的实际情况修改以下参数 -----
    VIDEO_FOLDER = r"F:\twitter_download\ShouldHaveCat"
    BASE_FILENAME = "海外猫咪视频大赏"
    STARTING_NUMBER = 102  # 起始编号，例如 11 代表 011
    FILE_EXTENSION = ".mp4"
    # ----- 参数修改结束 -----

    batch_rename_videos(VIDEO_FOLDER, BASE_FILENAME, STARTING_NUMBER, FILE_EXTENSION)

    # 提示用户按任意键退出，以便在直接运行脚本时查看输出
    input("\n按 Enter 键退出...")
