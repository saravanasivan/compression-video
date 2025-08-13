import os
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import shutil
import sys

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

        original_size = video_file.stat().st_size / (1024 * 1024)  # MB

        ffmpeg_cmd = [
            'ffmpeg',
            '-i', str(video_file),
            '-vcodec', 'libx264',
            '-crf', '28',
            '-preset', 'slow',
            '-acodec', 'aac',
            '-b:a', '128k',
            str(output_path)
        ]

        print(f"\nCompressing: {video_file.name}")
        process = subprocess.Popen(ffmpeg_cmd, stderr=subprocess.PIPE, universal_newlines=True)

        # Read FFmpeg stderr for progress
        total_duration = None
        for line in process.stderr:
            if "Duration" in line:
                # Extract total duration in seconds
                duration_str = line.strip().split("Duration:")[1].split(",")[0].strip()
                h, m, s = duration_str.split(":")
                total_duration = int(h) * 3600 + int(m) * 60 + float(s)
            if "time=" in line and total_duration:
                time_str = line.strip().split("time=")[1].split(" ")[0]
                try:
                    h, m, s = time_str.split(":")
                    elapsed = int(h) * 3600 + int(m) * 60 + float(s)
                    percent = (elapsed / total_duration) * 100
                    sys.stdout.write(f"\rProgress: {percent:.2f}%")
                    sys.stdout.flush()
                except:
                    pass

        process.wait()
        print("\nCompression finished.")

        compressed_size = output_path.stat().st_size / (1024 * 1024)  # MB
        print(f"Original Size: {original_size:.2f} MB → Compressed Size: {compressed_size:.2f} MB")

        messagebox.showinfo(
            "Compression Complete",
            f"File: {video_file.name}\n"
            f"Original Size: {original_size:.2f} MB\n"
            f"Compressed Size: {compressed_size:.2f} MB\n"
            f"Saved in:\n{output_folder}"
        )

def select_folder():
    folder_selected = filedialog.askdirectory(title="Select Folder Containing Videos")
    if folder_selected:
        compress_videos(folder_selected)

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # Hide main window
    root.after(100, select_folder)  # Delay folder dialog until Tkinter starts
    root.mainloop()
