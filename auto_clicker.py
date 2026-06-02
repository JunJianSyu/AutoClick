import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import pyautogui
from pynput import keyboard

pyautogui.FAILSAFE = False

KEY_LIST = [
    "F1", "F2", "F3", "F4", "F5", "F6",
    "F7", "F8", "F9", "F10", "F11", "F12",
    "A", "B", "C", "D", "E", "F", "G", "H", "I",
    "J", "K", "L", "M", "N", "O", "P", "Q", "R",
    "S", "T", "U", "V", "W", "X", "Y", "Z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "Enter", "Space", "Tab", "Escape", "Backspace",
    "Up", "Down", "Left", "Right",
    "Delete", "Home", "End", "PageUp", "PageDown",
]

MOUSE_ACTIONS = ["左键单击", "左键双击", "右键单击", "中键单击"]

HOTKEY_START = keyboard.Key.f9
HOTKEY_STOP = keyboard.Key.f10


class AutoClicker:
    def __init__(self):
        self.running = False
        self.paused = False
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

        self.key_sequence = []

        self._build_ui()
        self._start_hotkey_listener()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("自动按键/鼠标点击工具")
        self.root.geometry("420x560")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # --- 按键序列列表 ---
        seq_frame = ttk.LabelFrame(main, text="按键序列", padding=5)
        seq_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        list_inner = ttk.Frame(seq_frame)
        list_inner.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_inner)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.seq_listbox = tk.Listbox(list_inner, height=8, yscrollcommand=scrollbar.set,
                                       font=("", 9))
        self.seq_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.seq_listbox.yview)

        # 添加/删除按钮
        seq_btn_frame = ttk.Frame(seq_frame)
        seq_btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(seq_btn_frame, text="添加按键", command=self._add_key).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(seq_btn_frame, text="添加鼠标", command=self._add_mouse).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(seq_btn_frame, text="添加延迟", command=self._add_delay).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(seq_btn_frame, text="删除选中", command=self._remove_selected).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # 上下移动
        move_frame = ttk.Frame(seq_frame)
        move_frame.pack(fill=tk.X, pady=(3, 0))
        ttk.Button(move_frame, text="上移", command=self._move_up).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(move_frame, text="下移", command=self._move_down).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # --- 循环设置 ---
        loop_frame = ttk.LabelFrame(main, text="循环设置", padding=5)
        loop_frame.pack(fill=tk.X, pady=(0, 5))

        row1 = ttk.Frame(loop_frame)
        row1.pack(fill=tk.X)
        ttk.Label(row1, text="循环间隔(秒):").pack(side=tk.LEFT)
        self.interval = tk.DoubleVar(value=1.0)
        ttk.Spinbox(row1, from_=0.01, to=60.0, increment=0.1,
                    textvariable=self.interval, width=8, format="%.2f").pack(
                        side=tk.LEFT, padx=(5, 15))

        ttk.Label(row1, text="循环次数:").pack(side=tk.LEFT)
        self.loop_count = tk.IntVar(value=0)
        ttk.Spinbox(row1, from_=0, to=99999, increment=1,
                    textvariable=self.loop_count, width=8).pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(loop_frame, text="(循环次数为0表示无限循环)", font=("", 8)).pack(anchor=tk.W)

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
        ttk.Label(status_frame, textvariable=self.status_var, font=("", 10, "bold")).pack()

        # --- 热键提示 ---
        hint_frame = ttk.LabelFrame(main, text="热键提示", padding=5)
        hint_frame.pack(fill=tk.X)

        tk.Label(hint_frame, text="F9  - 开始/恢复", fg="green", font=("", 9)).pack(anchor=tk.W)
        tk.Label(hint_frame, text="F10 - 停止", fg="red", font=("", 9)).pack(anchor=tk.W)

    def _add_key(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("添加按键")
        dialog.geometry("280x150")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        ttk.Label(dialog, text="选择按键:").pack(pady=(10, 0))
        key_var = tk.StringVar(value="F5")
        ttk.Combobox(dialog, textvariable=key_var, values=KEY_LIST,
                      state="readonly", width=15).pack(pady=5)

        ttk.Label(dialog, text="按下持续时间(秒, 0为瞬按):").pack()
        dur_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(dialog, from_=0.0, to=10.0, increment=0.1,
                    textvariable=dur_var, width=8, format="%.2f").pack(pady=2)

        def confirm():
            self.key_sequence.append({
                "type": "key",
                "value": key_var.get(),
                "duration": dur_var.get(),
            })
            self._refresh_list()
            dialog.destroy()

        ttk.Button(dialog, text="确定", command=confirm).pack(pady=8)

    def _add_mouse(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("添加鼠标点击")
        dialog.geometry("300x220")
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
        ttk.Checkbutton(pos_frame, text="指定坐标", variable=use_pos).pack(anchor=tk.W)

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

        def confirm():
            action = {
                "type": "mouse",
                "value": mouse_var.get(),
                "use_pos": use_pos.get(),
                "x": x_var.get(),
                "y": y_var.get(),
            }
            self.key_sequence.append(action)
            self._refresh_list()
            dialog.destroy()

        ttk.Button(dialog, text="确定", command=confirm).pack(pady=8)

    def _add_delay(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("添加延迟")
        dialog.geometry("250x100")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        ttk.Label(dialog, text="延迟时间(秒):").pack(pady=(10, 0))
        delay_var = tk.DoubleVar(value=0.5)
        ttk.Spinbox(dialog, from_=0.01, to=60.0, increment=0.1,
                    textvariable=delay_var, width=8, format="%.2f").pack(pady=5)

        def confirm():
            self.key_sequence.append({
                "type": "delay",
                "value": delay_var.get(),
            })
            self._refresh_list()
            dialog.destroy()

        ttk.Button(dialog, text="确定", command=confirm).pack(pady=5)

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
            if t == "key":
                dur = action.get("duration", 0)
                dur_str = f" (持续{dur}秒)" if dur > 0 else ""
                self.seq_listbox.insert(tk.END, f"{i}. 按键: {action['value']}{dur_str}")
            elif t == "mouse":
                pos_str = ""
                if action.get("use_pos"):
                    pos_str = f" @({action['x']},{action['y']})"
                self.seq_listbox.insert(tk.END, f"{i}. 鼠标: {action['value']}{pos_str}")
            elif t == "delay":
                self.seq_listbox.insert(tk.END, f"{i}. 延迟: {action['value']}秒")

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

        interval = self.interval.get()
        max_loops = self.loop_count.get()
        loop_num = 0

        while not self.stop_event.is_set():
            if max_loops > 0 and loop_num >= max_loops:
                self.root.after(0, self._stop)
                self.root.after(0, lambda: self._set_status("完成"))
                return

            self.pause_event.wait()
            if self.stop_event.is_set():
                break

            for action in self.key_sequence:
                if self.stop_event.is_set():
                    return
                self.pause_event.wait()
                if self.stop_event.is_set():
                    break

                try:
                    t = action["type"]
                    if t == "key":
                        self._simulate_key(action["value"], action.get("duration", 0))
                    elif t == "mouse":
                        self._simulate_click(action)
                    elif t == "delay":
                        self._interruptible_sleep(action["value"])
                except Exception as e:
                    self.root.after(0, lambda err=str(e): self._set_status(f"错误: {err}"))
                    return

            loop_num += 1
            self.root.after(0, lambda n=loop_num: self._set_status(
                f"运行中... 已循环 {n} 次"))

            self._interruptible_sleep(interval)

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

    def _start(self):
        if not self.key_sequence:
            messagebox.showwarning("提示", "请先添加按键序列")
            return

        if self.paused:
            self.paused = False
            self.pause_event.set()
            self._set_status(f"运行中... (间隔: {self.interval.get()}秒)")
            self.pause_btn.config(state=tk.NORMAL)
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
        self._set_status(f"运行中... (间隔: {self.interval.get()}秒)")

        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def _pause(self):
        if not self.running or self.paused:
            return
        self.paused = True
        self.pause_event.clear()
        self._set_status("已暂停")
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED)

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

    # --- 全局热键 (pynput) ---

    def _start_hotkey_listener(self):
        def on_press(key):
            if key == HOTKEY_START:
                self.root.after(0, self._start)
            elif key == HOTKEY_STOP:
                self.root.after(0, self._stop)

        self.hotkey_listener = keyboard.Listener(on_press=on_press)
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

    def _on_close(self):
        self.stop_event.set()
        self.pause_event.set()
        if hasattr(self, "hotkey_listener"):
            self.hotkey_listener.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = AutoClicker()
    app.run()
