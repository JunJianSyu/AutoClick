# AutoClick
自动按键工具，专注走位
```
def _create_tray_icon_image(color=None):
    """加载自定义托盘图标"""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base_dir, "assets", "tray_icon.ico")
    return Image.open(icon_path)
```
图标文件放在 autoClick/assets/tray_icon.ico（推荐 64x64 或 32x32 的 .ico 格式）

```
pyinstaller --onefile --noconsole --icon=assets\icon.ico --name AutoClicker auto_clicker.py
--icon=assets\icon.ico 
```
这个参数已经加上了，把图标文件放到 autoClick/assets/icon.ico 即可

iconarchive.com、findicons.com 下载
