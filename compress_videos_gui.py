import os
import re
import sys
import shutil
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from queue import Queue, Empty

# ---------------- Configuration ----------------
VIDEO_EXTS = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv')
CRF_VALUE = "28"          # Lower = higher quality, larger size (typical: 23–28)
PRESET = "slow"           # faster | fast | medium | slow | slower | veryslow
AUDIO_BITRATE = "128k"    # AAC bitrate
# ------------------------------------------------

DURATION_PAT = re.compile(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)')
TIME_PAT     = re.compile(r'time=(\d+):(\d+):(\d+(?:\.\d+)?)')

def human_mb(bytes_val: int) -> float:
    return bytes_val / (1024 * 1024)

class VideoCompressorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Video Compressor")
        self.root.geometry("560x420")

        # --- Top: Buttons ---
        header = ttk.Label(self.root, text="Choose how you want to compress:", font=("Segoe UI", 12))
        header.pack(pady=(10, 8))

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack()

        self.btn_files = ttk.Button(btn_frame, text="Select Files", command=self.on_select_files, width=20)
        self.btn_files.grid(row=0, column=0, padx=8, pady=4)

        self.btn_folder = ttk.Button(btn_frame, text="Select Folder", command=self.on_select_folder, width=20)
        self.btn_folder.grid(row=0, column=1, padx=8, pady=4)

        # --- Progress widgets ---
        sep = ttk.Separator(self.root)
        sep.pack(fill="x", pady=10)

        self.lbl_current = ttk.Label(self.root, text="Current file: —")
        self.lbl_current.pack(anchor="w", padx=12)

        self.file_progress = ttk.Progressbar(self.root, orient="horizontal", length=520, mode="determinate", maximum=100)
        self.file_progress.pack(padx=12, pady=(4, 10))

        self.lbl_file_pct = ttk.Label(self.root, text="File progress: 0.00%")
        self.lbl_file_pct.pack(anchor="w", padx=12)

        self.overall_progress = ttk.Progressbar(self.root, orient="horizontal", length=520, mode="determinate", maximum=100)
        self.overall_progress.pack(padx=12, pady=(12, 4))

        self.lbl_overall = ttk.Label(self.root, text="Overall progress: 0.00% (0/0)")
        self.lbl_overall.pack(anchor="w", padx=12)

        # --- Log area (simple, read-only) ---
        log_label = ttk.Label(self.root, text="Log:")
        log_label.pack(anchor="w", padx=12, pady=(10, 2))

        self.txt_log = tk.Text(self.root, height=10, wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.txt_log.configure(state="disabled")

        # State & queue
        self.event_q: Queue = Queue()
        self.worker_thread: threading.Thread | None = None
        self.total_files = 0
        self.done_files = 0
        self.summary_lines: list[str] = []

        # Start polling queue
        self.root.after(100, self._poll_queue)

    # ---------- UI helpers ----------
    def log(self, msg: str, newline=True):
        # Terminal
        print(msg if newline else msg, end="" if not newline else "\n")
        # GUI log
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", msg + ("\n" if newline else ""))
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_files.configure(state=state)
        self.btn_folder.configure(state=state)

    # ---------- Selection handlers ----------
    def on_select_files(self):
        paths = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv *.flv *.wmv")]
        )
        if paths:
            file_list = [Path(p) for p in paths]
            self._start_compression(file_list, mode="files")

    def on_select_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing Videos")
        if folder:
            folder_path = Path(folder)
            file_list = [p for p in folder_path.iterdir() if p.suffix.lower() in VIDEO_EXTS and p.is_file()]
            if not file_list:
                messagebox.showinfo("No Videos", "No video files found in the selected folder.")
                return
            self._start_compression(file_list, mode="folder")

    # ---------- Start compression ----------
    def _start_compression(self, file_list: list[Path], mode: str):
        if not shutil.which("ffmpeg"):
            messagebox.showerror("FFmpeg Not Found", "FFmpeg is not installed or not in your system PATH.")
            return

        # Decide output folder
        if mode == "folder":
            parent = file_list[0].parent
            out_dir = parent.parent / f"{parent.name}_compressed"
        else:
            # For files selection: create sibling 'compressed' in the parent of the first file
            out_dir = file_list[0].parent / "compressed"

        out_dir.mkdir(exist_ok=True, parents=True)

        # Reset UI
        self.set_buttons_enabled(False)
        self.file_progress["value"] = 0
        self.overall_progress["value"] = 0
        self.lbl_file_pct.config(text="File progress: 0.00%")
        self.lbl_overall.config(text=f"Overall progress: 0.00% (0/{len(file_list)})")
        self.lbl_current.config(text="Current file: —")
        self.summary_lines.clear()
        self.done_files = 0
        self.total_files = len(file_list)
        self.log(f"🛠️ Starting compression of {len(file_list)} file(s) → {out_dir}")

        # Launch worker
        self.worker_thread = threading.Thread(
            target=self._worker_compress_batch,
            args=(file_list, out_dir),
            daemon=True
        )
        self.worker_thread.start()

    # ---------- Worker thread ----------
    def _worker_compress_batch(self, files: list[Path], out_dir: Path):
        for idx, src in enumerate(files, start=1):
            dst = out_dir / src.name
            self._compress_single(src, dst, idx, len(files))

        # Done
        self.event_q.put(("batch_done", None))

    def _compress_single(self, src: Path, dst: Path, idx: int, total: int):
        original_size_mb = human_mb(src.stat().st_size)
        self.event_q.put(("file_start", (src.name, idx, total, original_size_mb)))

        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(src),
            "-vcodec", "libx264",
            "-crf", CRF_VALUE,
            "-preset", PRESET,
            "-acodec", "aac",
            "-b:a", AUDIO_BITRATE,
            str(dst)
        ]

        # Start process (capture stderr for progress parsing)
        try:
            proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, universal_newlines=True)
        except FileNotFoundError:
            self.event_q.put(("error", f"Could not run ffmpeg. Ensure it's installed and on PATH."))
            return

        total_duration = None

        # Print to terminal too
        print(f"\n🔄 Compressing ({idx}/{total}): {src.name}")
        print(f"Original size: {original_size_mb:.2f} MB")

        for line in proc.stderr:
            # Duration
            if total_duration is None:
                dm = DURATION_PAT.search(line)
                if dm:
                    h, m, s = dm.groups()
                    total_duration = int(h) * 3600 + int(m) * 60 + float(s)
                    # Log detection
                    self.event_q.put(("duration", total_duration))

            # Progress time
            tm = TIME_PAT.search(line)
            if tm and total_duration:
                h, m, s = tm.groups()
                elapsed = int(h) * 3600 + int(m) * 60 + float(s)
                pct = max(0.0, min(100.0, (elapsed / total_duration) * 100.0))
                # Update GUI + Terminal
                self.event_q.put(("progress", pct))
                # Terminal rolling percentage
                sys.stdout.write(f"\rProgress: {pct:.2f}%")
                sys.stdout.flush()

        proc.wait()
        print("\n✅ Done!")

        # Sizes & summary
        try:
            compressed_size_mb = human_mb(dst.stat().st_size)
        except FileNotFoundError:
            self.event_q.put(("error", f"Output file missing for {src.name}."))
            return

        saved_pct = ((original_size_mb - compressed_size_mb) / original_size_mb) * 100 if original_size_mb > 0 else 0.0
        # Send to GUI
        self.event_q.put(("file_done", (src.name, original_size_mb, compressed_size_mb, saved_pct)))

        # Terminal info
        print(f"Compressed size: {compressed_size_mb:.2f} MB")
        print(f"Saved {saved_pct:.1f}% space")

    # ---------- Queue polling (runs on GUI thread) ----------
    def _poll_queue(self):
        try:
            while True:
                evt, data = self.event_q.get_nowait()

                if evt == "file_start":
                    name, idx, total, orig_mb = data
                    self.lbl_current.config(text=f"Current file: ({idx}/{total}) {name}")
                    self.file_progress["value"] = 0
                    self.lbl_file_pct.config(text="File progress: 0.00%")
                    self.log(f"• {name} — Original: {orig_mb:.2f} MB")

                elif evt == "duration":
                    # (Nothing to show; we just know we have total duration)
                    pass

                elif evt == "progress":
                    pct = float(data)
                    self.file_progress["value"] = pct
                    self.lbl_file_pct.config(text=f"File progress: {pct:.2f}%")

                elif evt == "file_done":
                    name, orig_mb, comp_mb, saved_pct = data
                    self.summary_lines.append(f"{name} — {orig_mb:.2f} MB → {comp_mb:.2f} MB (Saved {saved_pct:.1f}%)")
                    self.done_files += 1
                    overall_pct = (self.done_files / max(1, self.total_files)) * 100.0
                    self.overall_progress["value"] = overall_pct
                    self.lbl_overall.config(text=f"Overall progress: {overall_pct:.2f}% ({self.done_files}/{self.total_files})")
                    self.log(f"  ↳ Compressed: {comp_mb:.2f} MB (saved {saved_pct:.1f}%)")

                elif evt == "error":
                    self.set_buttons_enabled(True)
                    messagebox.showerror("Error", str(data))
                    self.log(f"ERROR: {data}")

                elif evt == "batch_done":
                    self.set_buttons_enabled(True)
                    summary = "\n".join(self.summary_lines) if self.summary_lines else "No files processed."
                    self.log("\n✅ All done!\n" + summary)
                    messagebox.showinfo("Compression Summary", f"All videos processed.\n\n{summary}")

        except Empty:
            # nothing to process right now
            pass

        # keep polling
        self.root.after(100, self._poll_queue)


def main():
    root = tk.Tk()

    # Use native-looking ttk theme if available
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass

    app = VideoCompressorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
