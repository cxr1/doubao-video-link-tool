import json
import os
import re
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk
from urllib.parse import parse_qs, urlparse

import requests
from requests import exceptions as req_exc


API_URL = "https://www.doubao.com/creativity/share/get_video_share_info"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Origin": "https://www.doubao.com",
    "Referer": "https://www.doubao.com/",
}


@dataclass
class VideoInfo:
    main_url: str
    backup_url: str
    width: int
    height: int
    definition: str
    poster_url: str
    prompt: str
    nickname: str
    user_id: str
    raw_data: dict


def tolerant_json_loads(text: str) -> dict:
    # Some responses may contain raw line breaks in fields like "prompt".
    return json.loads(text, strict=False)


def parse_share_input(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}

    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https"):
        q = parse_qs(parsed.query)
        return {
            "share_id": (q.get("share_id", [""]) or [""])[0].strip(),
            "video_id": (q.get("video_id", q.get("vid", [""])) or [""])[0].strip(),
            "creation_id": (q.get("creation_id", [""]) or [""])[0].strip(),
            "download_params": (q.get("download_params", [""]) or [""])[0].strip(),
        }

    share_match = re.search(r"share_id[=:]\s*([0-9]{6,})", raw)
    video_match = re.search(r"(video_id|vid)[=:]\s*([a-z0-9]{10,})", raw, re.I)
    if not share_match:
        share_match = re.search(r"\b([0-9]{6,})\b", raw)
    if not video_match:
        video_match = re.search(r"\b(v[0-9a-z]{10,})\b", raw, re.I)

    return {
        "share_id": (share_match.group(1) if share_match else "").strip(),
        "video_id": (video_match.group(2) if video_match and len(video_match.groups()) > 1 else (video_match.group(1) if video_match else "")).strip(),
        "creation_id": "",
        "download_params": "",
    }


class DoubaoClient:
    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def _post_once(self, payload: dict, headers: dict, trust_env: bool, verify: bool) -> requests.Response:
        session = requests.Session()
        session.trust_env = trust_env
        return session.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=self.timeout,
            verify=verify,
        )

    def request_share_info(self, share_id: str, video_id: str, creation_id: str = "", download_params: str = "", referer: str = "") -> dict:
        payload = {
            "share_id": share_id,
            "vid": video_id,
            "creation_id": creation_id or "",
        }
        if download_params:
            payload["download_params"] = download_params

        headers = dict(DEFAULT_HEADERS)
        if referer:
            headers["Referer"] = referer

        attempts = [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]

        last_error = None
        for trust_env, verify in attempts:
            try:
                resp = self._post_once(payload, headers, trust_env=trust_env, verify=verify)
                resp.raise_for_status()
                return tolerant_json_loads(resp.text)
            except (req_exc.RequestException, json.JSONDecodeError) as exc:
                last_error = exc
                continue

        raise RuntimeError(f"请求失败：{last_error}")

    def fetch_video_info(self, share_id: str, video_id: str, creation_id: str = "", download_params: str = "", referer: str = "") -> VideoInfo:
        data = self.request_share_info(
            share_id=share_id,
            video_id=video_id,
            creation_id=creation_id,
            download_params=download_params,
            referer=referer,
        )
        code = data.get("code")
        if code != 0:
            raise RuntimeError(f"接口返回失败，code={code} msg={data.get('msg', '')}")

        payload = data.get("data") or {}
        play_info = payload.get("play_info") or {}
        user_info = payload.get("user_info") or {}

        main_url = (play_info.get("main") or "").strip()
        backup_url = (play_info.get("backup") or "").strip()
        if not main_url and not backup_url:
            raise RuntimeError("未获取到视频链接（main/backup 均为空）")

        return VideoInfo(
            main_url=main_url,
            backup_url=backup_url,
            width=int(play_info.get("width") or 0),
            height=int(play_info.get("height") or 0),
            definition=(play_info.get("definition") or "").strip(),
            poster_url=(play_info.get("poster_url") or "").strip(),
            prompt=(payload.get("prompt") or "").strip(),
            nickname=(user_info.get("nickname") or "").strip(),
            user_id=str(user_info.get("user_id") or ""),
            raw_data=payload,
        )

    def _get_stream_once(self, url: str, headers: dict, trust_env: bool, verify: bool) -> requests.Response:
        session = requests.Session()
        session.trust_env = trust_env
        return session.get(
            url,
            headers=headers,
            stream=True,
            timeout=self.timeout,
            verify=verify,
        )

    def download_video(self, url: str, save_path: str, progress_cb=None):
        if not url:
            raise RuntimeError("下载链接为空")

        headers = {
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Accept": "*/*",
            "Range": "bytes=0-",
        }
        attempts = [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]

        last_error = None
        for trust_env, verify in attempts:
            try:
                with self._get_stream_once(url, headers, trust_env=trust_env, verify=verify) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("Content-Length") or 0)
                    downloaded = 0
                    with open(save_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_cb:
                                progress_cb(downloaded, total)
                return
            except (req_exc.RequestException, OSError) as exc:
                last_error = exc
                continue

        raise RuntimeError(f"下载失败：{last_error}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("豆包视频直链提取工具")
        self.geometry("920x680")
        self.minsize(860, 620)

        self.client = DoubaoClient()
        self.last_info = None
        self._busy = False
        self._downloading = False

        self.url_var = tk.StringVar()
        self.share_id_var = tk.StringVar()
        self.video_id_var = tk.StringVar()
        self.creation_id_var = tk.StringVar()
        self.status_var = tk.StringVar(value="请输入分享链接后点击“获取视频直链”")
        self.meta_var = tk.StringVar(value="分辨率：-")
        self.download_status_var = tk.StringVar(value="下载进度：-")

        self._build_ui()

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root, text="分享链接").grid(row=0, column=0, sticky="w")
        ttk.Entry(root, textvariable=self.url_var).grid(row=1, column=0, columnspan=5, sticky="ew", padx=(0, 8))
        ttk.Button(root, text="从链接提取参数", command=self.on_extract).grid(row=1, column=5, sticky="ew")

        ttk.Label(root, text="share_id").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Label(root, text="video_id").grid(row=2, column=2, sticky="w", pady=(10, 0))
        ttk.Label(root, text="creation_id (可选)").grid(row=2, column=4, sticky="w", pady=(10, 0))

        ttk.Entry(root, textvariable=self.share_id_var).grid(row=3, column=0, columnspan=2, sticky="ew", padx=(0, 8))
        ttk.Entry(root, textvariable=self.video_id_var).grid(row=3, column=2, columnspan=2, sticky="ew", padx=(0, 8))
        ttk.Entry(root, textvariable=self.creation_id_var).grid(row=3, column=4, columnspan=2, sticky="ew")

        ttk.Button(root, text="获取视频直链", command=self.on_fetch).grid(row=4, column=0, columnspan=6, sticky="ew", pady=(12, 8))

        ttk.Label(root, textvariable=self.status_var, foreground="#1f4f9c").grid(
            row=5, column=0, columnspan=6, sticky="w", pady=(2, 8)
        )
        ttk.Label(root, textvariable=self.meta_var).grid(row=6, column=0, columnspan=6, sticky="w", pady=(0, 8))

        ttk.Label(root, text="主链接（main）").grid(row=7, column=0, sticky="w")
        self.main_text = tk.Text(root, height=4, wrap="word")
        self.main_text.grid(row=8, column=0, columnspan=6, sticky="nsew")
        main_btns = ttk.Frame(root)
        main_btns.grid(row=9, column=0, columnspan=6, sticky="w", pady=(6, 0))
        ttk.Button(main_btns, text="复制", width=8, command=lambda: self.copy_text(self.main_text)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(main_btns, text="预览", width=8, command=lambda: self.on_preview(self.main_text)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(main_btns, text="下载", width=8, command=lambda: self.on_download("main", self.main_text)).pack(side=tk.LEFT)

        ttk.Label(root, text="备用链接（backup）").grid(row=10, column=0, sticky="w", pady=(10, 0))
        self.backup_text = tk.Text(root, height=4, wrap="word")
        self.backup_text.grid(row=11, column=0, columnspan=6, sticky="nsew")
        backup_btns = ttk.Frame(root)
        backup_btns.grid(row=12, column=0, columnspan=6, sticky="w", pady=(6, 0))
        ttk.Button(backup_btns, text="复制", width=8, command=lambda: self.copy_text(self.backup_text)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(backup_btns, text="预览", width=8, command=lambda: self.on_preview(self.backup_text)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(backup_btns, text="下载", width=8, command=lambda: self.on_download("backup", self.backup_text)).pack(side=tk.LEFT)

        ttk.Label(root, textvariable=self.download_status_var).grid(row=13, column=0, columnspan=6, sticky="w", pady=(10, 0))
        self.download_progress = ttk.Progressbar(root, orient="horizontal", mode="determinate", maximum=100)
        self.download_progress.grid(row=14, column=0, columnspan=6, sticky="ew")

        ttk.Label(root, text="提示词（prompt）").grid(row=15, column=0, sticky="w", pady=(10, 0))
        self.prompt_text = tk.Text(root, height=8, wrap="word")
        self.prompt_text.grid(row=16, column=0, columnspan=6, sticky="nsew")

        for col in range(6):
            root.columnconfigure(col, weight=1)
        root.rowconfigure(8, weight=1)
        root.rowconfigure(11, weight=1)
        root.rowconfigure(16, weight=2)

    def on_extract(self):
        info = parse_share_input(self.url_var.get())
        self.share_id_var.set(info.get("share_id", ""))
        self.video_id_var.set(info.get("video_id", ""))
        if info.get("creation_id"):
            self.creation_id_var.set(info.get("creation_id", ""))
        self.status_var.set("已尝试从链接提取参数，可手动修正后继续。")

    def on_fetch(self):
        if self._busy:
            return

        share_id = self.share_id_var.get().strip()
        video_id = self.video_id_var.get().strip()
        creation_id = self.creation_id_var.get().strip()

        if not share_id or not video_id:
            guessed = parse_share_input(self.url_var.get())
            share_id = share_id or guessed.get("share_id", "").strip()
            video_id = video_id or guessed.get("video_id", "").strip()
            if not creation_id:
                creation_id = guessed.get("creation_id", "").strip()
            self.share_id_var.set(share_id)
            self.video_id_var.set(video_id)
            self.creation_id_var.set(creation_id)

        if not share_id or not video_id:
            messagebox.showerror("参数不完整", "请提供有效的 share_id 和 video_id（可直接粘贴完整分享链接）。")
            return

        self.set_busy(True, "正在请求接口，请稍候...")
        threading.Thread(
            target=self._fetch_worker,
            args=(share_id, video_id, creation_id),
            daemon=True,
        ).start()

    def _fetch_worker(self, share_id: str, video_id: str, creation_id: str):
        try:
            parsed = parse_share_input(self.url_var.get())
            info = self.client.fetch_video_info(
                share_id=share_id,
                video_id=video_id,
                creation_id=creation_id,
                download_params=parsed.get("download_params", ""),
                referer=(self.url_var.get().strip() or ""),
            )
            self.after(0, lambda: self.on_fetch_success(info))
        except Exception as exc:
            self.after(0, lambda: self.on_fetch_error(str(exc)))

    def on_fetch_success(self, info: VideoInfo):
        self.last_info = info
        self.set_text(self.main_text, info.main_url)
        self.set_text(self.backup_text, info.backup_url)
        self.set_text(self.prompt_text, info.prompt)

        definition = info.definition or "-"
        size_str = f"{info.width}x{info.height}" if info.width and info.height else "-"
        self.meta_var.set(f"分辨率：{definition} ({size_str})")
        self.set_busy(False, "提取成功，可直接复制 main/backup 链接。")

    def on_fetch_error(self, err_msg: str):
        self.set_busy(False, f"提取失败：{err_msg}")
        messagebox.showerror("提取失败", err_msg)

    def set_busy(self, busy: bool, message: str):
        self._busy = busy
        self.status_var.set(message)

    def set_text(self, widget: tk.Text, content: str):
        widget.delete("1.0", tk.END)
        widget.insert("1.0", content or "")

    def copy_text(self, widget: tk.Text):
        value = widget.get("1.0", tk.END).strip()
        if not value:
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.status_var.set("已复制到剪贴板。")

    def on_preview(self, widget: tk.Text):
        url = widget.get("1.0", tk.END).strip()
        if not url:
            messagebox.showwarning("无法预览", "当前没有可预览的视频链接。")
            return
        webbrowser.open(url)
        self.status_var.set("已在默认浏览器打开视频预览。")

    def on_download(self, source: str, widget: tk.Text):
        if self._downloading:
            messagebox.showinfo("下载中", "当前已有下载任务，请稍候。")
            return

        url = widget.get("1.0", tk.END).strip()
        if not url:
            messagebox.showwarning("无法下载", "当前没有可下载的视频链接。")
            return

        share_id = self.share_id_var.get().strip() or "doubao"
        video_id = self.video_id_var.get().strip() or "video"
        default_name = f"{share_id}_{video_id}_{source}.mp4"
        save_path = filedialog.asksaveasfilename(
            title="保存视频",
            defaultextension=".mp4",
            initialfile=default_name,
            filetypes=[("MP4 视频", "*.mp4"), ("所有文件", "*.*")],
        )
        if not save_path:
            return

        self._downloading = True
        self.download_progress["value"] = 0
        self.download_status_var.set("下载进度：准备中...")
        self.status_var.set("正在下载视频，请稍候...")
        threading.Thread(target=self._download_worker, args=(url, save_path), daemon=True).start()

    def _download_worker(self, url: str, save_path: str):
        try:
            self.client.download_video(url, save_path, progress_cb=self._on_download_progress_thread)
            self.after(0, lambda: self._on_download_success(save_path))
        except Exception as exc:
            self.after(0, lambda: self._on_download_error(str(exc), save_path))

    def _on_download_progress_thread(self, downloaded: int, total: int):
        self.after(0, lambda: self._update_download_progress(downloaded, total))

    def _update_download_progress(self, downloaded: int, total: int):
        downloaded_mb = downloaded / (1024 * 1024)
        if total > 0:
            percent = min(100.0, downloaded * 100.0 / total)
            total_mb = total / (1024 * 1024)
            self.download_progress["value"] = percent
            self.download_status_var.set(f"下载进度：{percent:.1f}% ({downloaded_mb:.2f}MB / {total_mb:.2f}MB)")
        else:
            # Content-Length unknown: show downloaded size only.
            self.download_progress["value"] = 0
            self.download_status_var.set(f"下载进度：已下载 {downloaded_mb:.2f}MB")

    def _on_download_success(self, save_path: str):
        self._downloading = False
        self.download_progress["value"] = 100
        self.download_status_var.set(f"下载进度：完成，已保存到 {save_path}")
        self.status_var.set("下载完成。")
        messagebox.showinfo("下载完成", f"视频已保存到：\n{save_path}")

    def _on_download_error(self, err_msg: str, save_path: str):
        self._downloading = False
        try:
            if os.path.exists(save_path) and os.path.getsize(save_path) == 0:
                os.remove(save_path)
        except OSError:
            pass
        self.download_status_var.set(f"下载进度：失败（{err_msg}）")
        self.status_var.set("下载失败。")
        messagebox.showerror("下载失败", err_msg)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
