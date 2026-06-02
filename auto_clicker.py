import ctypes
import threading
import time
import tkinter as tk
from tkinter import ttk

# Windows API constants
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
WM_HOTKEY = 0x0312

VK_MAP = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44,
    "E": 0x45, "F": 0x46, "G": 0x47, "H": 0x48,
    "I": 0x49, "J": 0x4A, "K": 0x4B, "L": 0x4C,
    "M": 0x4D, "N": 0x4E, "O": 0x4F, "P": 0x50,
    "Q": 0x51, "R": 0x52, "S": 0x53, "T": 0x54,
    "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58,
    "Y": 0x59, "Z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33,
    "4": 0x34, "5": 0x35, "6": 0x36, "7": 0x37,
    "8": 0x38, "9": 0x39,
    "Enter": 0x0D, "Space": 0x20, "Tab": 0x09,
    "Esc": 0x1B, "Backspace": 0x08,
}

KEY_LIST = [
    "F1", "F2", "F3", "F4", "F5", "F6",
    "F7", "F8", "F9", "F10", "F11", "F12",
    "A", "B", "C", "D", "E", "F", "G", "H", "I",
    "J", "K", "L", "M", "N", "O", "P", "Q", "R",
    "S", "T", "U", "V", "W", "X", "Y", "Z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "Enter", "Space", "Tab", "Esc", "Backspace",
]

HOTKEY_START_ID = 1
HOTKEY_STOP_ID = 2
VK_F11 = 0x7A
VK_F12 = 0x7B


class AutoClicker:
    def __init__(self):
        self.running = False
        self.paused = False
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()

        self._build_ui()
        self._start_hotkey_listener()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("自动按键/鼠标点击工具")
        self.root.geometry("320x400")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Operation type ---
        type_frame = ttk.LabelFrame(main, text="操作类型", padding=5)
        type_frame.pack(fill=tk.X, pady=(0, 5))

        self.op_type = tk.StringVar(value="keyboard")
        ttk.Radiobutton(type_frame, text="键盘按键", variable=self.op_type,
                        value="keyboard", command=self._toggle_config).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(type_frame, text="鼠标点击", variable=self.op_type,
                        value="mouse", command=self._toggle_config).pack(side=tk.LEFT, padx=10)

        # --- Key config ---
        self.key_frame = ttk.LabelFrame(main, text="按键配置", padding=5)
        self.key_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(self.key_frame, text="选择按键:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.key_var = tk.StringVar(value="F5")
        self.key_combo = ttk.Combobox(self.key_frame, textvariable=self.key_var,
                                      values=KEY_LIST, state="readonly", width=15)
        self.key_combo.grid(row=0, column=1, pady=2, padx=(5, 0))

        ttk.Label(self.key_frame, text="自定义(hex):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.custom_vk = tk.StringVar()
        ttk.Entry(self.key_frame, textvariable=self.custom_vk, width=17).grid(
            row=1, column=1, pady=2, padx=(5, 0))

        # --- Mouse config ---
        self.mouse_frame = ttk.LabelFrame(main, text="鼠标配置", padding=5)

        ttk.Label(self.mouse_frame, text="鼠标按键:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.mouse_btn = tk.StringVar(value="左键")
        ttk.Combobox(self.mouse_frame, textvariable=self.mouse_btn,
                     values=["左键", "右键"], state="readonly", width=15).grid(
            row=0, column=1, pady=2, padx=(5, 0))

        # --- Interval ---
        interval_frame = ttk.LabelFrame(main, text="延迟间隔", padding=5)
        interval_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(interval_frame, text="间隔(秒):").pack(side=tk.LEFT)
        self.interval = tk.DoubleVar(value=1.0)
        ttk.Spinbox(interval_frame, from_=0.1, to=60.0, increment=0.1,
                    textvariable=self.interval, width=10, format="%.1f").pack(side=tk.LEFT, padx=(5, 0))

        # --- Buttons ---
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        self.start_btn = ttk.Button(btn_frame, text="开始", command=self._start)
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        self.pause_btn = ttk.Button(btn_frame, text="暂停", command=self._pause, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        # --- Status ---
        status_frame = ttk.LabelFrame(main, text="状态", padding=5)
        status_frame.pack(fill=tk.X, pady=(0, 5))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.status_var, font=("", 10, "bold")).pack()

        # --- Hotkey hints ---
        hint_frame = ttk.LabelFrame(main, text="热键提示", padding=5)
        hint_frame.pack(fill=tk.X)

        f11_label = tk.Label(hint_frame, text="F11 - 开始/恢复", fg="green", font=("", 9))
        f11_label.pack(anchor=tk.W)
        f12_label = tk.Label(hint_frame, text="F12 - 停止", fg="red", font=("", 9))
        f12_label.pack(anchor=tk.W)

    def _toggle_config(self):
        if self.op_type.get() == "keyboard":
            self.mouse_frame.pack_forget()
            self.key_frame.pack(fill=tk.X, pady=(0, 5),
                                after=self.root.nametowidget(self.key_frame.master).winfo_children()[0])
        else:
            self.key_frame.pack_forget()
            self.mouse_frame.pack(fill=tk.X, pady=(0, 5),
                                  after=self.root.nametowidget(self.mouse_frame.master).winfo_children()[0])

    def _get_vk_code(self):
        custom = self.custom_vk.get().strip()
        if custom:
            return int(custom, 16)
        return VK_MAP.get(self.key_var.get(), 0)

    def _simulate_key(self, vk):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

    def _simulate_click(self, button):
        if button == "左键":
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        else:
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

    def _worker(self):
        op = self.op_type.get()
        interval = self.interval.get()

        if op == "keyboard":
            vk = self._get_vk_code()
            if vk == 0:
                self.root.after(0, lambda: self._set_status("错误: 无效的按键配置"))
                return
            action = lambda: self._simulate_key(vk)
        else:
            btn = self.mouse_btn.get()
            action = lambda: self._simulate_click(btn)

        while not self.stop_event.is_set():
            self.pause_event.wait()
            if self.stop_event.is_set():
                break
            try:
                action()
            except Exception as e:
                self.root.after(0, lambda err=str(e): self._set_status(f"错误: {err}"))
                break

            elapsed = 0.0
            while elapsed < interval:
                if self.stop_event.is_set():
                    return
                time.sleep(min(0.05, interval - elapsed))
                elapsed += 0.05

    def _set_status(self, text):
        self.status_var.set(text)

    def _start(self):
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

    # --- Global hotkeys ---

    def _start_hotkey_listener(self):
        t = threading.Thread(target=self._hotkey_loop, daemon=True)
        t.start()

    def _hotkey_loop(self):
        user32 = ctypes.windll.user32
        user32.RegisterHotKey(None, HOTKEY_START_ID, 0, VK_F11)
        user32.RegisterHotKey(None, HOTKEY_STOP_ID, 0, VK_F12)

        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                if msg.wParam == HOTKEY_START_ID:
                    self.root.after(0, self._start)
                elif msg.wParam == HOTKEY_STOP_ID:
                    self.root.after(0, self._stop)

    def _on_close(self):
        self.stop_event.set()
        self.pause_event.set()
        try:
            user32 = ctypes.windll.user32
            user32.UnregisterHotKey(None, HOTKEY_START_ID)
            user32.UnregisterHotKey(None, HOTKEY_STOP_ID)
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = AutoClicker()
    app.run()
