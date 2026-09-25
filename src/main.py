"""
小说提取器 - 主程序
美观的UI界面，一键提取小说
"""
import os
import re
import sys
import threading
import queue
from urllib.parse import urlparse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

# ===== 高DPI清晰度设置 =====
# 必须在创建任何tkinter窗口之前设置
if sys.platform == 'win32':
    import ctypes
    try:
        # Windows 10+  Per-Monitor DPI Awareness
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except:
        try:
            # 旧版Windows
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass

# 添加src目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extractor import NovelExtractor


class NovelExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("📖 小说提取器 v2.2")
        self.root.geometry("1050x820")
        self.root.minsize(900, 700)

        # 设置主题色 - 更柔和的配色
        self.bg_color = "#faf8f5"           # 暖米色背景
        self.card_bg = "#ffffff"             # 卡片白色
        self.primary_color = "#8b4513"       # 棕褐色主色（书卷气）
        self.primary_light = "#a0522d"      # 浅棕
        self.accent_color = "#d2691e"       # 巧克力色强调
        self.success_color = "#2e7d32"      # 墨绿成功
        self.warning_color = "#f57c00"      # 橙色警告
        self.error_color = "#c62828"        # 深红错误
        self.text_dark = "#3e2723"          # 深棕文字
        self.text_muted = "#8d6e63"        # 浅棕灰辅助文字
        self.border_color = "#e0d0c0"      # 边框色

        self.root.configure(bg=self.bg_color)

        # 字体配置 - 楷体
        self.font_title = ("楷体", 24, "bold")
        self.font_subtitle = ("楷体", 11)
        self.font_label = ("楷体", 12, "bold")
        self.font_input = ("楷体", 11)
        self.font_button = ("楷体", 12, "bold")
        self.font_button_small = ("楷体", 10)
        self.font_log = ("Consolas", 9)
        self.font_status = ("楷体", 9)

        # 提取器实例
        self.extractor = None
        self.is_running = False
        self._ui_events = queue.Queue()
        self.chapters = []
        self.book_title = ""
        self.book_author = ""

        # 配置文件路径（exe同目录）
        # 打包成exe后用 sys.executable 的目录，脚本运行时用 __file__ 的目录
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包后的exe
            base_dir = os.path.dirname(sys.executable)
        else:
            # Python 脚本运行
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(base_dir, 'config.json')

        self._build_ui()
        self.root.after(50, self._process_ui_events)

    def _process_ui_events(self):
        """只在 Tk 主线程中处理后台任务发来的界面更新。"""
        try:
            while True:
                event, payload = self._ui_events.get_nowait()
                if event == "log":
                    self._append_log(payload)
                elif event == "progress":
                    self._apply_progress(*payload)
                elif event == "message":
                    kind, title, message = payload
                    getattr(messagebox, kind)(title, message)
                elif event == "controls":
                    self.start_btn.config(state=tk.NORMAL)
                    self.stop_btn.config(state=tk.DISABLED, bg="#d7ccc8")
        except queue.Empty:
            pass
        self.root.after(50, self._process_ui_events)

    def _build_ui(self):
        """构建UI界面"""
        # 主容器
        main_frame = tk.Frame(self.root, bg=self.bg_color, padx=25, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ===== 顶部标题区 =====
        header_frame = tk.Frame(main_frame, bg=self.bg_color)
        header_frame.pack(fill=tk.X, pady=(0, 20))

        # 大标题
        title_label = tk.Label(
            header_frame,
            text="📖 小说提取器",
            font=self.font_title,
            bg=self.bg_color,
            fg=self.primary_color
        )
        title_label.pack(side=tk.LEFT)

        # 副标题
        subtitle_label = tk.Label(
            header_frame,
            text="✦ 一键提取 · 自动识别 · 本地运行 ✦",
            font=self.font_subtitle,
            bg=self.bg_color,
            fg=self.text_muted
        )
        subtitle_label.pack(side=tk.RIGHT, pady=(15, 0))

        # ===== URL输入卡片 =====
        url_card = tk.Frame(main_frame, bg=self.card_bg, relief=tk.FLAT, bd=0)
        url_card.pack(fill=tk.X, pady=(0, 12))
        # 模拟卡片阴影效果
        url_card.config(highlightbackground=self.border_color, highlightthickness=1)

        tk.Label(
            url_card,
            text="🔗 小说目录网址",
            font=self.font_label,
            bg=self.card_bg,
            fg=self.primary_color
        ).pack(anchor=tk.W, padx=15, pady=(12, 5))

        url_inner = tk.Frame(url_card, bg=self.card_bg, padx=15)
        url_inner.pack(fill=tk.X, pady=(0, 12))

        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            url_inner,
            textvariable=self.url_var,
            font=self.font_input,
            relief=tk.SOLID,
            bd=1,
            bg="#fafaf5",
            fg=self.text_dark,
            insertbackground=self.primary_color
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        self.url_entry.insert(0, "请粘贴小说目录页网址...")

        # ===== 输出路径卡片 =====
        path_card = tk.Frame(main_frame, bg=self.card_bg, relief=tk.FLAT, bd=0)
        path_card.pack(fill=tk.X, pady=(0, 15))
        path_card.config(highlightbackground=self.border_color, highlightthickness=1)

        tk.Label(
            path_card,
            text="📁 输出文件夹",
            font=self.font_label,
            bg=self.card_bg,
            fg=self.primary_color
        ).pack(anchor=tk.W, padx=15, pady=(12, 5))

        path_inner = tk.Frame(path_card, bg=self.card_bg, padx=15)
        path_inner.pack(fill=tk.X, pady=(0, 12))

        # 默认输出路径：先读配置文件，没有就用桌面
        default_path = os.path.join(os.path.expanduser("~"), "Desktop", "小说提取")
        saved_path = self._load_config().get('output_path', '')
        self.path_var = tk.StringVar(value=saved_path or default_path)
        self.path_entry = tk.Entry(
            path_inner,
            textvariable=self.path_var,
            font=self.font_input,
            relief=tk.SOLID,
            bd=1,
            bg="#fafaf5",
            fg=self.text_dark,
            insertbackground=self.primary_color
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)

        browse_btn = tk.Button(
            path_inner,
            text="📂 浏览",
            command=self._browse_path,
            font=self.font_button_small,
            bg=self.primary_color,
            fg="white",
            relief=tk.FLAT,
            padx=18,
            pady=4,
            cursor="hand2"
        )
        browse_btn.pack(side=tk.RIGHT, padx=(10, 0))

        # ===== 按钮区域 =====
        btn_frame = tk.Frame(main_frame, bg=self.bg_color)
        btn_frame.pack(fill=tk.X, pady=(5, 15))

        self.start_btn = tk.Button(
            btn_frame,
            text="🚀 开始提取",
            command=self._start_extraction,
            font=self.font_button,
            bg=self.success_color,
            fg="white",
            relief=tk.FLAT,
            padx=35,
            pady=10,
            cursor="hand2"
        )
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = tk.Button(
            btn_frame,
            text="⏹ 停止",
            command=self._stop_extraction,
            font=self.font_button_small,
            bg="#d7ccc8",
            fg=self.text_muted,
            relief=tk.FLAT,
            padx=22,
            pady=8,
            state=tk.DISABLED,
            cursor="hand2"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=10)

        self.rules_btn = tk.Button(
            btn_frame,
            text="⚙ 规则管理",
            command=self._show_rules,
            font=self.font_button_small,
            bg=self.primary_color,
            fg="white",
            relief=tk.FLAT,
            padx=22,
            pady=8,
            cursor="hand2"
        )
        self.rules_btn.pack(side=tk.RIGHT)

        # ===== 进度区域 =====
        progress_card = tk.Frame(main_frame, bg=self.card_bg, relief=tk.FLAT, bd=0)
        progress_card.pack(fill=tk.X, pady=(0, 10))
        progress_card.config(highlightbackground=self.border_color, highlightthickness=1)

        tk.Label(
            progress_card,
            text="📊 提取进度",
            font=self.font_label,
            bg=self.card_bg,
            fg=self.primary_color
        ).pack(anchor=tk.W, padx=15, pady=(12, 5))

        progress_inner = tk.Frame(progress_card, bg=self.card_bg, padx=15)
        progress_inner.pack(fill=tk.X, pady=(0, 12))

        self.progress_var = tk.DoubleVar()
        # 自定义进度条样式
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor='#f0ebe0',
            background=self.accent_color,
            lightcolor=self.accent_color,
            darkcolor=self.accent_color,
            bordercolor=self.border_color,
            thickness=18
        )

        self.progress_bar = ttk.Progressbar(
            progress_inner,
            variable=self.progress_var,
            maximum=100,
            style="Custom.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill=tk.X, expand=True, side=tk.LEFT)

        self.progress_label = tk.Label(
            progress_inner,
            text="0%",
            font=self.font_button_small,
            bg=self.card_bg,
            fg=self.primary_color,
            width=8
        )
        self.progress_label.pack(side=tk.RIGHT, padx=(10, 0))

        # 状态文字
        self.status_label = tk.Label(
            main_frame,
            text="✨ 就绪 - 输入小说目录网址开始提取",
            font=self.font_subtitle,
            bg=self.bg_color,
            fg=self.text_muted
        )
        self.status_label.pack(anchor=tk.W, pady=(0, 8))

        # ===== 日志区域 =====
        log_card = tk.Frame(main_frame, bg=self.card_bg, relief=tk.FLAT, bd=0)
        log_card.pack(fill=tk.BOTH, expand=True)
        log_card.config(highlightbackground=self.border_color, highlightthickness=1)

        tk.Label(
            log_card,
            text="📜 运行日志",
            font=self.font_label,
            bg=self.card_bg,
            fg=self.primary_color
        ).pack(anchor=tk.W, padx=15, pady=(12, 5))

        log_inner = tk.Frame(log_card, bg=self.card_bg, padx=15)
        log_inner.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        self.log_text = tk.Text(
            log_inner,
            font=self.font_log,
            bg="#2d1f14",
            fg="#e8d5b7",
            relief=tk.FLAT,
            wrap=tk.WORD,
            insertbackground=self.accent_color,
            padx=10,
            pady=8
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(log_inner, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        # ===== 底部状态栏 =====
        status_bar = tk.Frame(self.root, bg=self.primary_color, height=30)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_bar.pack_propagate(False)

        self.status_bar_label = tk.Label(
            status_bar,
            text="  ✨ 就绪 | 小说提取器 v2.2",
            font=self.font_status,
            bg=self.primary_color,
            fg="white"
        )
        self.status_bar_label.pack(side=tk.LEFT, padx=10)

        self.status_bar_right = tk.Label(
            status_bar,
            text="📚 自动适配 · 智能识别 · 本地运行  ",
            font=self.font_status,
            bg=self.primary_color,
            fg="#e0d0c0"
        )
        self.status_bar_right.pack(side=tk.RIGHT, padx=10)

    def _load_config(self):
        """读取配置文件"""
        import json
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except:
            pass
        return {}

    def _save_config(self, key: str, value: str):
        """保存配置到文件"""
        import json
        config = self._load_config()
        config[key] = value
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _browse_path(self):
        """选择输出文件夹"""
        current = self.path_var.get()
        path = filedialog.askdirectory(title="📁 选择输出文件夹", initialdir=current)
        if path:
            self.path_var.set(path)
            self._save_config('output_path', path)

    def _show_rules(self):
        """显示规则管理窗口"""
        if not self.extractor:
            self.extractor = NovelExtractor(log_callback=self.log)

        rules = self.extractor.get_saved_rules()

        dialog = tk.Toplevel(self.root)
        dialog.title("⚙ 规则管理")
        dialog.geometry("650x450")
        dialog.configure(bg=self.bg_color)
        dialog.transient(self.root)

        # 标题
        tk.Label(
            dialog,
            text="🌐 已保存的网站适配规则",
            font=("楷体", 16, "bold"),
            bg=self.bg_color,
            fg=self.primary_color
        ).pack(pady=(20, 8))

        # 说明
        tk.Label(
            dialog,
            text="程序会自动学习并保存成功的网站适配规则，下次访问同网站时自动使用",
            font=("楷体", 10),
            bg=self.bg_color,
            fg=self.text_muted,
            wraplength=600
        ).pack(pady=(0, 15))

        # 规则列表
        list_frame = tk.Frame(dialog, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=(0, 15))

        if not rules:
            tk.Label(
                list_frame,
                text="📭 暂无已保存的规则\n\n提取过的网站会自动添加到这里",
                font=("楷体", 12),
                bg=self.card_bg,
                fg="#999"
            ).pack(expand=True)
        else:
            columns = ("域名", "章节选择器", "正文选择器")
            tree = ttk.Treeview(list_frame, columns=columns, show="headings")
            tree.heading("域名", text="🌐 网站域名")
            tree.heading("章节选择器", text="📑 章节选择器")
            tree.heading("正文选择器", text="📄 正文选择器")
            tree.column("域名", width=200)
            tree.column("章节选择器", width=200)
            tree.column("正文选择器", width=200)

            for domain, rule in rules.items():
                tree.insert("", tk.END, values=(
                    domain,
                    rule.get('chapter_selector', '—'),
                    rule.get('content_selector', '—')
                ))

            scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscroll=scrollbar.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        # 底部按钮
        btn_frame = tk.Frame(dialog, bg=self.bg_color)
        btn_frame.pack(pady=(0, 20))

        tk.Button(
            btn_frame,
            text="❌ 关闭",
            command=dialog.destroy,
            font=("楷体", 10),
            bg=self.primary_color,
            fg="white",
            relief=tk.FLAT,
            padx=25,
            pady=6,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=8)

        tk.Button(
            btn_frame,
            text="🗑 清空所有规则",
            command=lambda: self._clear_rules(dialog),
            font=("楷体", 10),
            bg=self.error_color,
            fg="white",
            relief=tk.FLAT,
            padx=25,
            pady=6,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=8)

    def _clear_rules(self, dialog):
        """清空所有规则"""
        if messagebox.askyesno("确认", "确定要清空所有已保存的网站规则吗？"):
            self.extractor.rules = {}
            self.extractor._save_rules()
            dialog.destroy()
            messagebox.showinfo("完成", "所有规则已清空")

    def log(self, message: str):
        """添加日志"""
        if threading.current_thread() is not threading.main_thread():
            self._ui_events.put(("log", message))
            return
        self._append_log(message)

    def _append_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def set_progress(self, percent: float, status: str = ""):
        """更新进度"""
        if threading.current_thread() is not threading.main_thread():
            self._ui_events.put(("progress", (percent, status)))
            return
        self._apply_progress(percent, status)

    def _apply_progress(self, percent: float, status: str = ""):
        self.progress_var.set(percent)
        self.progress_label.config(text=f"{percent:.1f}%")
        if status:
            self.status_label.config(text=f"✨ {status}")
            self.status_bar_label.config(text=f"  {status} | 小说提取器 v2.2")
        self.root.update_idletasks()

    def _start_extraction(self):
        """开始提取"""
        url = self.url_var.get().strip()
        output_path = self.path_var.get().strip()

        if not url or url == "请粘贴小说目录页网址...":
            messagebox.showwarning("提示", "请输入小说目录网址")
            return

        parsed_url = urlparse(url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            messagebox.showwarning("网址无效", "请输入以 http:// 或 https:// 开头的有效网址")
            return

        if not output_path:
            messagebox.showwarning("提示", "请选择输出文件夹")
            return

        if not os.path.exists(output_path):
            os.makedirs(output_path)

        # 记住输出路径
        self._save_config('output_path', output_path)

        # 切换按钮状态
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL, bg=self.error_color, fg="white")
        self.is_running = True

        # 启动后台线程
        thread = threading.Thread(target=self._extraction_worker, args=(url, output_path), daemon=True)
        thread.start()

    def _stop_extraction(self):
        """停止提取"""
        self.is_running = False
        self.log("⏹ 正在停止...")
        self.stop_btn.config(state=tk.DISABLED, bg="#d7ccc8")

    def _extraction_worker(self, url: str, output_path: str):
        """后台提取工作线程"""
        try:
            self.log("=" * 50)
            self.log("🚀 开始提取小说...")
            self.set_progress(0, "正在获取章节列表...")

            self.extractor = NovelExtractor(
                log_callback=self.log,
                progress_callback=self.set_progress,
                stop_callback=lambda: not self.is_running
            )

            # 获取章节列表
            chapters, title, author = self.extractor.get_chapter_list(url)
            self.book_title = title
            self.book_author = author

            if not chapters:
                self.log("❌ 错误: 未找到任何章节，请检查网址是否正确")
                self._ui_events.put(("message", ("showerror", "错误", "未找到任何章节，请检查网址是否正确")))
                return

            total = len(chapters)
            self.log(f"📚 共 {total} 章，开始提取内容...")

            # 逐章提取
            all_chapters_content = []
            for i, (ch_title, ch_url) in enumerate(chapters):
                if not self.is_running:
                    self.log("⏹ 已停止提取")
                    break

                self.set_progress((i / total) * 90, f"正在提取: {ch_title}")
                self.log(f"[{i+1}/{total}] {ch_title}")

                content = self.extractor.extract_chapter_content(ch_url, ch_title)
                all_chapters_content.append((ch_title, content))

            if not self.is_running:
                return

            # 校验内容
            self.set_progress(92, "正在校验内容...")
            self.log("\n🔍 开始内容校验...")
            validation = self.extractor.validate_content(all_chapters_content)

            self.log(f"\n📊 === 校验结果 ===")
            self.log(f"   总章节数: {validation['total']}")
            self.log(f"   ✅ 正常章节: {validation['normal']}")
            self.log(f"   ⚠️  内容过短: {validation['too_short']}")
            self.log(f"   ❌ 提取失败: {validation['empty']}")

            if validation['too_short'] > 0:
                self.log("\n⚠️  内容过短的章节:")
                for item in validation['details']:
                    if item['issues']:
                        self.log(f"   - {item['title']} ({item['chars']}字): {', '.join(item['issues'])}")

            # 保存文件
            self.set_progress(96, "正在保存文件...")
            self.log("\n💾 正在保存文件...")

            filename = f"{title}_{author}.txt"
            filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename).strip(" .")
            if not filename:
                filename = "小说.txt"
            filepath = os.path.join(output_path, filename)
            if os.path.exists(filepath):
                stem, extension = os.path.splitext(filepath)
                suffix = 2
                while os.path.exists(f"{stem} ({suffix}){extension}"):
                    suffix += 1
                filepath = f"{stem} ({suffix}){extension}"

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"《{title}》\n作者：{author}\n\n")
                for ch_title, content in all_chapters_content:
                    f.write(content + "\n\n" + "=" * 50 + "\n\n")

            file_size = os.path.getsize(filepath) / 1024
            self.log(f"\n📁 文件已保存: {filepath}")
            self.log(f"📏 文件大小: {file_size:.1f} KB")

            self.set_progress(100, "提取完成!")
            self.log("\n✅ 提取完成!")

            self._ui_events.put(("message", (
                "showinfo", "🎉 提取完成",
                f"📖 书名: {title}\n✍️ 作者: {author}\n📚 章节数: {validation['total']}\n📏 文件大小: {file_size:.1f} KB\n\n📁 保存位置:\n{filepath}"
            )))

        except Exception as e:
            self.log(f"\n❌ 错误: {str(e)}")
            self._ui_events.put(("message", ("showerror", "错误", f"提取过程中出现错误:\n{str(e)}")))
        finally:
            self.is_running = False
            self._ui_events.put(("controls", None))


def main():
    root = tk.Tk()
    app = NovelExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
