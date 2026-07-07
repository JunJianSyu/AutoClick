from __future__ import annotations

import json
import logging
import os
import random
import sys
import threading
import time
import tkinter as tk

import pyautogui
from PIL import Image, ImageDraw, ImageFont
from pynput import keyboard
import pystray

pyautogui.FAILSAFE = False

MOUSE_ACTIONS = {
    "左键单击": "left",
    "左键双击": "left",
    "右键单击": "right",
    "中键单击": "middle",
}

MIN_INTERVAL = 0.01  # 秒，防止 CPU 打满
MAX_INTERVAL = 3600.0

DEFAULT_CONFIG = {
    "hotkey_start": "F1",
    "hotkey_stop": "F2",
    "key_sequence": [],
}


# ---------------------------------------------------------------------------
# 路径 / 日志 / 配置
# ---------------------------------------------------------------------------
def _get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_config_path():
    return os.path.join(_get_base_dir(), "auto_clicker_config.json")


def _get_log_path():
    return os.path.join(_get_base_dir(), "auto_clicker.log")


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(_get_log_path(), encoding="utf-8"),
        ],
    )


logger = logging.getLogger("auto_clicker")


def _normalize_action(action):
    """规范化单个 action，返回 (action_or_None, error_msg)"""
    if not isinstance(action, dict):
        return None, "action 不是对象"
    t = action.get("type")
    interval = action.get("interval", 1.0)
    try:
        interval = float(interval)
    except (TypeError, ValueError):
        return None, "interval 不是数字"
    interval = max(MIN_INTERVAL, min(MAX_INTERVAL, interval))
    action["interval"] = interval

    # 通用：interval 随机抖动 (0-1)，表示上下浮动比例
    jitter = action.get("jitter", 0)
    try:
        jitter = float(jitter)
    except (TypeError, ValueError):
        jitter = 0
    action["jitter"] = max(0.0, min(1.0, jitter))

    if t == "key":
        value = action.get("value")
        if not isinstance(value, str) or not value.strip():
            return None, "key.value 为空"
        duration = action.get("duration", 0)
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            duration = 0
        action["duration"] = max(0.0, duration)
        return action, None

    if t == "mouse":
        value = action.get("value")
        if value not in MOUSE_ACTIONS:
            return None, f"未知鼠标操作: {value}"
        if action.get("use_pos"):
            try:
                action["x"] = int(action.get("x", 0))
                action["y"] = int(action.get("y", 0))
            except (TypeError, ValueError):
                return None, "坐标不是整数"
            # 坐标抖动 (像素)
            pj = action.get("position_jitter", 0)
            try:
                pj = int(pj)
            except (TypeError, ValueError):
                pj = 0
            action["position_jitter"] = max(0, pj)
        return action, None

    return None, f"未知 type: {t}"


def load_config():
    path = _get_config_path()
    if not os.path.exists(path):
        save_config(DEFAULT_CONFIG)
        logger.info("配置文件不存在，已创建默认配置: %s", path)
        return DEFAULT_CONFIG.copy()
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("配置文件读取失败(%s)，使用默认配置", e)
        return DEFAULT_CONFIG.copy()

    for key, val in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = val

    # 规范化按键序列
    raw_seq = config.get("key_sequence") or []
    if not isinstance(raw_seq, list):
        raw_seq = []
    valid = []
    for i, action in enumerate(raw_seq):
        normalized, err = _normalize_action(dict(action) if isinstance(action, dict) else {})
        if normalized:
            valid.append(normalized)
        else:
            logger.warning("跳过无效 action[%d]: %s", i, err)
    config["key_sequence"] = valid
    return config


def save_config(config):
    try:
        with open(_get_config_path(), "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.warning("配置保存失败: %s", e)


# ---------------------------------------------------------------------------
# 单实例锁
# ---------------------------------------------------------------------------
_lock_file = None


def _acquire_single_instance() -> bool:
    """尝试获取单实例锁。返回 True 表示获取成功。"""
    global _lock_file
    lock_path = os.path.join(_get_base_dir(), ".auto_clicker.lock")
    try:
        if sys.platform == "win32":
            import msvcrt
            _lock_file = open(lock_path, "w")
            try:
                msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                _lock_file.close()
                _lock_file = None
                return False
        else:
            import fcntl
            _lock_file = open(lock_path, "w")
            try:
                fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except OSError:
                _lock_file.close()
                _lock_file = None
                return False
    except Exception as e:
        logger.warning("单实例锁失败(%s)，跳过检测", e)
        return True


# ---------------------------------------------------------------------------
# 应用状态与工作线程
# ---------------------------------------------------------------------------
class AppState:
    """封装运行时状态，避免全局变量散落"""

    STATES = {
        "ready":   ("#9E9E9E", "就绪"),
        "running": ("#4CAF50", "运行中"),
        "paused":  ("#FF9800", "已暂停"),
        "stopped": ("#F44336", "已停止"),
        "empty":   ("#9E9E9E", "无配置"),
        "error":   ("#F44336", "配置错误"),
    }

    def __init__(self):
        self.running = False
        self.paused = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.workers: list[threading.Thread] = []
        self.generation = 0  # 每次 start 递增，避免旧线程混入
        self.lock = threading.Lock()

        # UI 引用（在 build_ui 后填充）
        self.root: tk.Tk | None = None
        self.dot: tk.Label | None = None
        self.status_var: tk.StringVar | None = None
        self.tray_icon = None

        # 配置引用
        self.config = {}
        self.key_sequence: list = []
        self.hotkey_listener = None

    def set_state(self, state: str):
        if not self.root:
            return
        color, text = self.STATES.get(state, self.STATES["ready"])
        try:
            self.root.after(0, lambda: self._apply_state_ui(color, text))
        except tk.TclError:
            pass

    def _apply_state_ui(self, color, text):
        if self.dot and self.status_var:
            try:
                self.dot.config(fg=color)
                self.status_var.set(text)
            except tk.TclError:
                pass


state = AppState()


def _interruptible_sleep(duration):
    """可被 stop_event 打断的 sleep"""
    if duration <= 0:
        return
    end_time = time.monotonic() + duration
    while True:
        remaining = end_time - time.monotonic()
        if remaining <= 0:
            return
        if state.stop_event.is_set():
            return
        state.pause_event.wait()
        time.sleep(min(0.05, remaining))


def _simulate_key(key_name, duration=0):
    name = key_name.lower()
    if duration > 0:
        pyautogui.keyDown(name)
        time.sleep(duration)
        pyautogui.keyUp(name)
    else:
        pyautogui.press(name)


def _simulate_click(action):
    value = action["value"]
    x, y = None, None
    if action.get("use_pos"):
        x, y = action.get("x"), action.get("y")
        pj = action.get("position_jitter", 0)
        if pj > 0 and x is not None and y is not None:
            x += random.randint(-pj, pj)
            y += random.randint(-pj, pj)
    button = MOUSE_ACTIONS.get(value, "left")
    if value == "左键双击":
        pyautogui.doubleClick(x=x, y=y, button=button)
    else:
        pyautogui.click(x=x, y=y, button=button)


def _action_worker(action, my_generation):
    """单个 action 的循环执行线程"""
    base_interval = action.get("interval", 1.0)
    jitter = action.get("jitter", 0)
    while not state.stop_event.is_set() and my_generation == state.generation:
        state.pause_event.wait()
        if state.stop_event.is_set() or my_generation != state.generation:
            break
        start_time = time.monotonic()
        try:
            t = action["type"]
            if t == "key":
                _simulate_key(action["value"], action.get("duration", 0))
            elif t == "mouse":
                _simulate_click(action)
        except Exception as e:
            logger.warning("执行 action 失败 [%s=%s]: %s",
                           action.get("type"), action.get("value"), e)
            # 继续下一轮而非退出，除非是致命错误
        # 计算本轮 interval（可选随机抖动）
        interval = base_interval
        if jitter > 0:
            interval *= (1 + random.uniform(-jitter, jitter))
        interval = max(MIN_INTERVAL, interval)
        elapsed = time.monotonic() - start_time
        remaining = max(0, interval - elapsed)
        _interruptible_sleep(remaining)


def do_start():
    with state.lock:
        if not state.key_sequence:
            logger.info("按键序列为空，无法启动")
            state.set_state("empty")
            return

        if state.running and not state.paused:
            return  # 已经在跑

        if state.paused:
            # 恢复
            state.paused = False
            state.pause_event.set()
            state.set_state("running")
            return

        # 首次启动，先确保上一轮线程已退出
        state.generation += 1
        my_gen = state.generation
        state.stop_event.clear()
        state.pause_event.set()
        state.running = True
        state.paused = False
        state.set_state("running")

        state.workers = []
        for action in state.key_sequence:
            t = threading.Thread(
                target=_action_worker, args=(action, my_gen), daemon=True
            )
            t.start()
            state.workers.append(t)
        logger.info("已启动 %d 个 worker", len(state.workers))


def do_pause():
    with state.lock:
        if not state.running or state.paused:
            return
        state.paused = True
        state.pause_event.clear()
        state.set_state("paused")


def do_stop():
    with state.lock:
        if not state.running and not state.paused:
            return
        state.stop_event.set()
        state.pause_event.set()  # 唤醒暂停中的线程让它退出
        state.running = False
        state.paused = False
        state.set_state("stopped")


# ---------------------------------------------------------------------------
# 热键
# ---------------------------------------------------------------------------
def _parse_hotkey(name):
    if not isinstance(name, str):
        return None
    name = name.strip().upper()
    if name.startswith("F"):
        try:
            n = int(name[1:])
            if 1 <= n <= 24:
                return getattr(keyboard.Key, f"f{n}")
        except (ValueError, AttributeError):
            return None
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name.lower())
    return None


def _start_hotkey_listener():
    start_key = _parse_hotkey(state.config.get("hotkey_start", "F1"))
    stop_key = _parse_hotkey(state.config.get("hotkey_stop", "F2"))

    if not start_key:
        logger.warning("hotkey_start 无效")
    if not stop_key:
        logger.warning("hotkey_stop 无效")

    def on_press(key):
        try:
            if start_key and key == start_key:
                if state.running and not state.paused:
                    state.root.after(0, do_pause)
                else:
                    state.root.after(0, do_start)
            elif stop_key and key == stop_key:
                state.root.after(0, do_stop)
        except Exception as e:
            logger.warning("热键处理异常: %s", e)

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    state.hotkey_listener = listener


# ---------------------------------------------------------------------------
# 浮动指示器
# ---------------------------------------------------------------------------
def _build_indicator(root: tk.Tk):
    indicator = tk.Toplevel(root)
    indicator.overrideredirect(True)
    indicator.attributes("-topmost", True)
    indicator.geometry("+10+10")

    frame = tk.Frame(indicator, bg="#2b2b2b",
                     highlightbackground="#555555", highlightthickness=1)
    frame.pack(fill=tk.BOTH, expand=True)

    dot = tk.Label(frame, text="\u25cf", fg="#9E9E9E",
                   bg="#2b2b2b", font=("", 10))
    dot.pack(side=tk.LEFT, padx=(6, 2))

    status_var = tk.StringVar(value="就绪")
    label = tk.Label(frame, textvariable=status_var,
                     fg="#ffffff", bg="#2b2b2b",
                     font=("", 10, "bold"))
    label.pack(side=tk.LEFT, padx=(0, 6), pady=3)

    return dot, status_var


# ---------------------------------------------------------------------------
# 托盘图标
# ---------------------------------------------------------------------------
def _create_icon_image(color="#4CAF50"):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 59, 59], radius=12, fill=color)
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "A", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (64 - tw) // 2 - bbox[0]
    y = (64 - th) // 2 - bbox[1]
    draw.text((x, y), "A", fill="white", font=font)
    return img


def _reload_config(icon=None, item=None):
    """重新加载配置文件"""
    def _do():
        try:
            state.config = load_config()
            state.key_sequence = state.config.get("key_sequence", [])
            # 停止当前运行的任务（配置变了）
            do_stop()
            # 重启热键监听（热键可能变了）
            if state.hotkey_listener:
                state.hotkey_listener.stop()
            _start_hotkey_listener()
            if not state.key_sequence:
                state.set_state("empty")
            else:
                state.set_state("ready")
            logger.info("配置已重新加载，共 %d 个 action", len(state.key_sequence))
        except Exception as e:
            logger.error("重新加载配置失败: %s", e)
            state.set_state("error")
    if state.root:
        state.root.after(0, _do)


def _quit_app(icon=None, item=None):
    do_stop()
    try:
        if state.hotkey_listener:
            state.hotkey_listener.stop()
    except Exception:
        pass
    if state.tray_icon:
        state.tray_icon.stop()
    if state.root:
        state.root.after(0, state.root.destroy)


def _start_tray():
    icon = pystray.Icon(
        "auto_clicker",
        icon=_create_icon_image(),
        title="AutoClicker",
        menu=pystray.Menu(
            pystray.MenuItem("重新加载配置", _reload_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", _quit_app),
        ),
    )
    state.tray_icon = icon
    thread = threading.Thread(target=icon.run, daemon=True)
    thread.start()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    _setup_logging()
    logger.info("=== AutoClicker 启动 ===")

    if not _acquire_single_instance():
        logger.warning("已有实例在运行，退出")
        sys.exit(0)

    # 加载配置
    state.config = load_config()
    state.key_sequence = state.config.get("key_sequence", [])

    # 构建 UI（tkinter 必须在主线程）
    state.root = tk.Tk()
    state.root.withdraw()
    state.dot, state.status_var = _build_indicator(state.root)

    # 启动热键监听
    _start_hotkey_listener()

    # 延迟启动托盘（等主循环起来）
    state.root.after(200, _start_tray)

    # 初始状态
    if not state.key_sequence:
        state.set_state("empty")
        logger.info("配置为空，请编辑 %s 后从托盘'重新加载配置'", _get_config_path())
    else:
        state.set_state("ready")
        logger.info("已加载 %d 个 action", len(state.key_sequence))

    try:
        state.root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("=== AutoClicker 退出 ===")


if __name__ == "__main__":
    main()
