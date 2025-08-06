import os
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import shutil

def compress_videos(input_folder_path):
    input_folder = Path(input_folder_path)

    if not input_folder.exists() or not input_folder.is_dir():
        messagebox.showerror("Error", "Invalid folder path.")
        return

    # Check if ffmpeg is available
    if not shutil.which("ffmpeg"):
        messagebox.showerror("FFmpeg Not Found", "FFmpeg is not installed or not in your system PATH.")
        return

    output_folder = input_folder.parent / f"{input_folder.name}_compressed"
    output_folder.mkdir(exist_ok=True)

    video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv')
    video_files = [f for f in input_folder.iterdir() if f.suffix.lower() in video_extensions]

    if not video_files:
        messagebox.showinfo("No Videos", "No video files found in the selected folder.")
        return

    for video_file in video_files:
        output_path = output_folder / video_file.name

        ffmpeg_cmd = [
            'ffmpeg',
            '-i', str(video_file),
            '-vcodec', 'libx264',
            '-crf', '28',           # You can lower this (e.g., 23–26) for higher quality
            '-preset', 'slow',
            '-acodec', 'aac',
            '-b:a', '128k',
            str(output_path)
        ]

        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    messagebox.showinfo("Done", f"Compression complete.\nCompressed videos saved in:\n{output_folder}")

def select_folder():
    folder_selected = filedialog.askdirectory(title="Select Folder Containing Videos")
    if folder_selected:
        compress_videos(folder_selected)

# GUI launcher
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    select_folder()
