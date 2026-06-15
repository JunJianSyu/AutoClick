import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import pyautogui
from pynput import keyboard

pyautogui.FAILSAFE = False

MOUSE_ACTIONS = ["左键单击", "左键双击", "右键单击", "中键单击"]

# F1-F12 保留给热键使用，不允许设为动作键
RESERVED_HOTKEY_NAMES = {f"f{i}" for i in range(1, 13)}


class AutoClicker:
    def __init__(self):
        self.running = False
        self.paused = False
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

        self.key_sequence = []
        self.floating_indicator = None

        self._build_ui()
        self._start_hotkey_listener()

    def _build_ui(self):
        self.root = tk.Tk()
        self.hotkey_start_var = tk.StringVar(value="F9")
        self.hotkey_stop_var = tk.StringVar(value="F10")
        self.root.title("自动按键/鼠标点击工具")
        self.root.geometry("420x480")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_window_unmap)
        self.root.bind("<Map>", self._on_window_map)

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # --- 按键序列列表 ---
        seq_frame = ttk.LabelFrame(main, text="按键序列 (每个按键独立循环)", padding=5)
        seq_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        list_inner = ttk.Frame(seq_frame)
        list_inner.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_inner)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.seq_listbox = tk.Listbox(list_inner, height=8, yscrollcommand=scrollbar.set,
                                      font=("", 9))
        self.seq_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.seq_listbox.yview)

        seq_btn_frame = ttk.Frame(seq_frame)
        seq_btn_frame.pack(fill=tk.X, pady=(5, 0))

        self.add_key_btn = ttk.Button(
            seq_btn_frame, text="添加按键", command=self._add_key)
        self.add_key_btn.pack(side=tk.LEFT, expand=True,
                              fill=tk.X, padx=(0, 2))
        self.add_mouse_btn = ttk.Button(
            seq_btn_frame, text="添加鼠标", command=self._add_mouse)
        self.add_mouse_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(seq_btn_frame, text="删除选中", command=self._remove_selected).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        move_frame = ttk.Frame(seq_frame)
        move_frame.pack(fill=tk.X, pady=(3, 0))
        ttk.Button(move_frame, text="上移", command=self._move_up).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(move_frame, text="下移", command=self._move_down).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # --- 控制按钮 ---
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        self.start_btn = ttk.Button(btn_frame, text="开始", command=self._start)
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        self.pause_btn = ttk.Button(btn_frame, text="暂停", command=self._pause,
                                    state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop,
                                   state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # --- 状态 ---
        status_frame = ttk.LabelFrame(main, text="状态", padding=5)
        status_frame.pack(fill=tk.X, pady=(0, 5))

        self.status_var = tk.StringVar(value="就绪 - 请添加按键序列")
        ttk.Label(status_frame, textvariable=self.status_var,
                  font=("", 10, "bold")).pack()

        # --- 热键设置 ---
        hotkey_frame = ttk.LabelFrame(main, text="热键设置 (F1-F12 保留给热键)", padding=5)
        hotkey_frame.pack(fill=tk.X)

        row1 = ttk.Frame(hotkey_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="开始/暂停:").pack(side=tk.LEFT)
        self.start_hk_label = ttk.Label(row1, textvariable=self.hotkey_start_var,
                                         fg="green", font=("", 9, "bold"), width=8)
        self.start_hk_label.pack(side=tk.LEFT, padx=(5, 5))
        ttk.Button(row1, text="修改", width=5,
                   command=lambda: self._capture_hotkey("start")).pack(side=tk.LEFT)

        row2 = ttk.Frame(hotkey_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="停止:").pack(side=tk.LEFT)
        self.stop_hk_label = ttk.Label(row2, textvariable=self.hotkey_stop_var,
                                        fg="red", font=("", 9, "bold"), width=8)
        self.stop_hk_label.pack(side=tk.LEFT, padx=(5, 5))
        ttk.Button(row2, text="修改", width=5,
                   command=lambda: self._capture_hotkey("stop")).pack(side=tk.LEFT)

    def _add_key(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("添加按键")
        dialog.geometry("280x200")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        ttk.Label(dialog, text="输入按键 (F1-F12 不可用):").pack(pady=(10, 0))
        key_var = tk.StringVar(value="space")
        ttk.Entry(dialog, textvariable=key_var, width=18).pack(pady=5)

        ttk.Label(dialog, text="按下持续时间(秒, 0为瞬按):").pack()
        dur_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(dialog, from_=0.0, to=10.0, increment=0.1,
                    textvariable=dur_var, width=8, format="%.2f").pack(pady=2)

        ttk.Label(dialog, text="执行间隔(秒):").pack()
        interval_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(dialog, from_=0.01, to=60.0, increment=0.1,
                    textvariable=interval_var, width=8, format="%.2f").pack(pady=2)

        def confirm():
            key_name = key_var.get().strip()
            if not key_name:
                messagebox.showwarning("提示", "请输入按键名称", parent=dialog)
                return
            if key_name.lower() in RESERVED_HOTKEY_NAMES:
                messagebox.showwarning("提示",
                                        "F1-F12 保留给热键使用，不可作为动作按键",
                                        parent=dialog)
                return
            self.key_sequence.append({
                "type": "key",
                "value": key_name,
                "duration": dur_var.get(),
                "interval": interval_var.get(),
            })
            self._refresh_list()
            dialog.destroy()

        ttk.Button(dialog, text="确定", command=confirm).pack(pady=8)

    def _add_mouse(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("添加鼠标点击")
        dialog.geometry("300x270")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        ttk.Label(dialog, text="鼠标操作:").pack(pady=(10, 0))
        mouse_var = tk.StringVar(value="左键单击")
        ttk.Combobox(dialog, textvariable=mouse_var, values=MOUSE_ACTIONS,
                     state="readonly", width=15).pack(pady=5)

        pos_frame = ttk.Frame(dialog)
        pos_frame.pack(pady=5)

        use_pos = tk.BooleanVar(value=False)
        ttk.Checkbutton(pos_frame, text="指定坐标",
                        variable=use_pos).pack(anchor=tk.W)

        coord_frame = ttk.Frame(pos_frame)
        coord_frame.pack(anchor=tk.W, padx=(20, 0))
        ttk.Label(coord_frame, text="X:").pack(side=tk.LEFT)
        x_var = tk.IntVar(value=0)
        ttk.Spinbox(coord_frame, from_=0, to=9999, textvariable=x_var, width=6).pack(
            side=tk.LEFT, padx=(2, 10))
        ttk.Label(coord_frame, text="Y:").pack(side=tk.LEFT)
        y_var = tk.IntVar(value=0)
        ttk.Spinbox(coord_frame, from_=0, to=9999, textvariable=y_var, width=6).pack(
            side=tk.LEFT, padx=2)

        def pick_pos():
            dialog.withdraw()
            self.root.after(1500, lambda: _capture_pos())

        def _capture_pos():
            x, y = pyautogui.position()
            x_var.set(x)
            y_var.set(y)
            use_pos.set(True)
            dialog.deiconify()

        ttk.Button(pos_frame, text="1.5秒后捕获鼠标位置", command=pick_pos).pack(
            anchor=tk.W, padx=(20, 0), pady=(3, 0))

        ttk.Label(dialog, text="执行间隔(秒):").pack()
        interval_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(dialog, from_=0.01, to=60.0, increment=0.1,
                    textvariable=interval_var, width=8, format="%.2f").pack(pady=2)

        def confirm():
            self.key_sequence.append({
                "type": "mouse",
                "value": mouse_var.get(),
                "use_pos": use_pos.get(),
                "x": x_var.get(),
                "y": y_var.get(),
                "interval": interval_var.get(),
            })
            self._refresh_list()
            dialog.destroy()

        ttk.Button(dialog, text="确定", command=confirm).pack(pady=8)

    def _remove_selected(self):
        selected = self.seq_listbox.curselection()
        if not selected:
            return
        for idx in reversed(selected):
            self.key_sequence.pop(idx)
        self._refresh_list()

    def _move_up(self):
        selected = self.seq_listbox.curselection()
        if not selected or selected[0] == 0:
            return
        idx = selected[0]
        self.key_sequence[idx - 1], self.key_sequence[idx] = \
            self.key_sequence[idx], self.key_sequence[idx - 1]
        self._refresh_list()
        self.seq_listbox.selection_set(idx - 1)

    def _move_down(self):
        selected = self.seq_listbox.curselection()
        if not selected or selected[0] >= len(self.key_sequence) - 1:
            return
        idx = selected[0]
        self.key_sequence[idx + 1], self.key_sequence[idx] = \
            self.key_sequence[idx], self.key_sequence[idx + 1]
        self._refresh_list()
        self.seq_listbox.selection_set(idx + 1)

    def _refresh_list(self):
        self.seq_listbox.delete(0, tk.END)
        for i, action in enumerate(self.key_sequence, 1):
            t = action["type"]
            interval = action.get("interval", 1.0)
            if t == "key":
                dur = action.get("duration", 0)
                dur_str = f" 持续{dur}秒" if dur > 0 else ""
                self.seq_listbox.insert(tk.END,
                                        f"{i}. 按键: {action['value']}{dur_str} | 间隔{interval}秒")
            elif t == "mouse":
                pos_str = ""
                if action.get("use_pos"):
                    pos_str = f" @({action['x']},{action['y']})"
                self.seq_listbox.insert(tk.END,
                                        f"{i}. 鼠标: {action['value']}{pos_str} | 间隔{interval}秒")
        self._update_add_buttons()

    def _update_add_buttons(self):
        state = tk.NORMAL if len(self.key_sequence) < 5 else tk.DISABLED
        self.add_key_btn.config(state=state)
        self.add_mouse_btn.config(state=state)

    def _simulate_key(self, key_name, duration=0):
        name = key_name.lower()
        if duration > 0:
            pyautogui.keyDown(name)
            time.sleep(duration)
            pyautogui.keyUp(name)
        else:
            pyautogui.press(name)

    def _simulate_click(self, action):
        value = action["value"]
        x, y = None, None
        if action.get("use_pos"):
            x, y = action["x"], action["y"]

        if value == "左键单击":
            pyautogui.click(x=x, y=y, button="left")
        elif value == "左键双击":
            pyautogui.doubleClick(x=x, y=y, button="left")
        elif value == "右键单击":
            pyautogui.click(x=x, y=y, button="right")
        elif value == "中键单击":
            pyautogui.click(x=x, y=y, button="middle")

    def _worker(self):
        if not self.key_sequence:
            self.root.after(0, lambda: self._set_status("错误: 按键序列为空"))
            return

        threads = []
        for action in self.key_sequence:
            t = threading.Thread(target=self._action_worker,
                                 args=(action,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

    def _action_worker(self, action):
        interval = action.get("interval", 1.0)

        while not self.stop_event.is_set():
            self.pause_event.wait()
            if self.stop_event.is_set():
                break

            start_time = time.monotonic()
            try:
                t = action["type"]
                if t == "key":
                    self._simulate_key(
                        action["value"], action.get("duration", 0))
                elif t == "mouse":
                    self._simulate_click(action)
            except Exception as e:
                self.root.after(0, lambda err=str(
                    e): self._set_status(f"错误: {err}"))
                return

            # 间隔 = 两次执行之间的总时间，扣除本次执行耗时
            elapsed = time.monotonic() - start_time
            remaining = max(0, interval - elapsed)
            self._interruptible_sleep(remaining)

    def _interruptible_sleep(self, duration):
        elapsed = 0.0
        step = 0.05
        while elapsed < duration:
            if self.stop_event.is_set():
                return
            self.pause_event.wait()
            time.sleep(min(step, duration - elapsed))
            elapsed += step

    def _set_status(self, text):
        self.status_var.set(text)

    # --- 最小化浮动指示器 ---

    def _on_window_unmap(self, event):
        """主窗口最小化时触发"""
        if event.widget is self.root and self.running:
            self._show_indicator()

    def _on_window_map(self, event):
        """主窗口恢复时触发"""
        if event.widget is self.root:
            self._hide_indicator()

    def _show_indicator(self):
        """显示左上角浮动运行指示器"""
        if self.floating_indicator and self.floating_indicator.winfo_exists():
            return
        self.floating_indicator = tk.Toplevel(self.root)
        self.floating_indicator.overrideredirect(True)
        self.floating_indicator.attributes("-topmost", True)
        self.floating_indicator.geometry("+10+10")

        frame = tk.Frame(self.floating_indicator, bg="#2b2b2b",
                         highlightbackground="#555555", highlightthickness=1)
        frame.pack(fill=tk.BOTH, expand=True)

        dot = tk.Label(frame, text="\u25cf", fg="#4CAF50" if not self.paused else "#FF9800",
                       bg="#2b2b2b", font=("", 10))
        dot.pack(side=tk.LEFT, padx=(6, 2))

        self.indicator_text = tk.StringVar(
            value="运行中" if not self.paused else "已暂停")
        label = tk.Label(frame, textvariable=self.indicator_text,
                         fg="#ffffff", bg="#2b2b2b",
                         font=("", 10, "bold"), cursor="hand2")
        label.pack(side=tk.LEFT, padx=(0, 6), pady=3)

        # 点击指示器恢复主窗口
        for widget in (frame, label, dot):
            widget.bind("<Button-1>", self._restore_from_indicator)

    def _hide_indicator(self):
        """销毁浮动指示器"""
        if self.floating_indicator and self.floating_indicator.winfo_exists():
            self.floating_indicator.destroy()
        self.floating_indicator = None

    def _restore_from_indicator(self, event=None):
        """点击指示器恢复主窗口"""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self._hide_indicator()

    def _start(self):
        if not self.key_sequence:
            messagebox.showwarning("提示", "请先添加按键序列")
            return

        if self.paused:
            self.paused = False
            self.pause_event.set()
            self._set_status("运行中...")
            self.start_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL)
            # 如果最小化中，更新指示器
            if self.root.state() == "iconic" and self.floating_indicator \
                    and self.floating_indicator.winfo_exists():
                self.indicator_text.set("运行中")
            return

        if self.running:
            return

        self.running = True
        self.paused = False
        self.stop_event.clear()
        self.pause_event.set()

        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL)
        self._set_status("运行中...")

        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

        # 如果启动时已最小化，显示指示器
        if self.root.state() == "iconic":
            self._show_indicator()

    def _pause(self):
        if not self.running or self.paused:
            return
        self.paused = True
        self.pause_event.clear()
        self._set_status("已暂停")
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        # 更新浮动指示器
        if self.floating_indicator and self.floating_indicator.winfo_exists():
            self.indicator_text.set("已暂停")
        elif self.root.state() == "iconic":
            self._show_indicator()

    def _stop(self):
        if not self.running:
            return
        self.stop_event.set()
        self.pause_event.set()
        self.running = False
        self.paused = False

        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.DISABLED)
        self._set_status("已停止")
        self._hide_indicator()

    # --- 全局热键 (pynput) ---

    @staticmethod
    def _is_valid_hotkey(name):
        """检查是否为合法热键名：F13-F24 或单字符"""
        name = name.strip().upper()
        if name.startswith("F"):
            try:
                n = int(name[1:])
                return 13 <= n <= 24
            except ValueError:
                return False
        return len(name) == 1

    @staticmethod
    def _parse_hotkey(name):
        """将热键名解析为 pynput Key 对象"""
        name = name.strip().upper()
        if name.startswith("F"):
            try:
                n = int(name[1:])
                return getattr(keyboard.Key, f"f{n}")
            except (ValueError, AttributeError):
                return None
        if len(name) == 1:
            return keyboard.KeyCode.from_char(name.lower())
        return None

    def _capture_hotkey(self, which):
        """弹出对话框捕获新热键"""
        dialog = tk.Toplevel(self.root)
        dialog.title("设置热键")
        dialog.geometry("260x120")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        ttk.Label(dialog, text="请按下要设置的热键\n(支持 F1-F24 或单个字符键)",
                  font=("", 10)).pack(pady=10)
        result_var = tk.StringVar(value="等待按键...")
        ttk.Label(dialog, textvariable=result_var,
                  font=("", 12, "bold"), fg="blue").pack()

        captured = [None]

        def on_key_press(key):
            if hasattr(key, 'name'):
                key_name = key.name.upper()
                if key_name in (f"F{i}" for i in range(1, 25)):
                    result_var.set(key_name)
                    captured[0] = key_name
                    dialog.after(300, dialog.destroy)
                    return
            if hasattr(key, 'char') and key.char:
                result_var.set(key.char.upper())
                captured[0] = key.char.upper()
                dialog.after(300, dialog.destroy)

        temp_listener = keyboard.Listener(on_press=on_key_press)
        temp_listener.start()

        dialog.wait_window()
        temp_listener.stop()

        if captured[0]:
            if which == "start":
                self.hotkey_start_var.set(captured[0])
            else:
                self.hotkey_stop_var.set(captured[0])
            self._restart_hotkey_listener()

    def _restart_hotkey_listener(self):
        """重启热键监听器以应用新的热键配置"""
        if hasattr(self, "hotkey_listener"):
            self.hotkey_listener.stop()
        self._start_hotkey_listener()

    def _start_hotkey_listener(self):
        start_key = self._parse_hotkey(self.hotkey_start_var.get())
        stop_key = self._parse_hotkey(self.hotkey_stop_var.get())

        def on_press(key):
            if start_key and key == start_key:
                if self.running and not self.paused:
                    self.root.after(0, self._pause)
                else:
                    self.root.after(0, self._start)
            elif stop_key and key == stop_key:
                self.root.after(0, self._stop)

        self.hotkey_listener = keyboard.Listener(on_press=on_press)
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

    def _on_close(self):
        self.stop_event.set()
        self.pause_event.set()
        self._hide_indicator()
        if hasattr(self, "hotkey_listener"):
            self.hotkey_listener.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = AutoClicker()
    app.run()
