# Claude 娘桌宠悬浮窗 · macOS 版
# 本文件是 composition root：组装 settings / core / platform，平台细节都在 platform/mac/。
# 状态文件、设置文件和 Windows 版 pet.pyw 保持同一套约定。
# 用法：python pet_mac.py <运行目录>
import os
import socket
import sys
import time

from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
from Foundation import NSTimer

from core import cli_args
from core import errors as core_errors
from core import sessions as core_sessions
from core import state_reader as core_state_reader
from core import view_model as core_view_model
from core.models import IDLE_AFTER, SIZES, SPRITES  # noqa: F401  (测试从入口锁定契约)
from platforms.mac import focus
from platforms.mac import window as mac_window
from platforms.mac.menu import PetMenu
from platforms.mac.notify import play_sound

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS = os.path.join(os.path.dirname(HERE), 'sounds')
# --shot <路径> 里的路径是截图输出位置，不是运行目录
RUN_DIR, SHOT_PATH = cli_args.parse_args(sys.argv[1:], cli_args.default_run_dir())
SESSIONS = os.path.join(RUN_DIR, 'sessions')
SETTINGS = os.path.join(RUN_DIR, 'settings.json')

# 只允许开一个桌宠：占住一个本地端口，占不到说明已经有一个在跑
# （在 acquire_lock() 里做，保持 import 本模块无副作用，测试才能导入）
_lock = None


def acquire_lock():
    global _lock
    try:
        _lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock.bind(('127.0.0.1', 47321))
    except OSError:
        sys.exit(0)


def load_settings():
    return core_state_reader.load_settings(SETTINGS)


def save_settings(s):
    core_state_reader.save_settings(SETTINGS, s)


def read_latest():
    """读所有会话里最新的状态；顺手清掉过期文件。"""
    return core_sessions.read_latest(SESSIONS)


class Pet:
    """应用控制器：持有状态与定时器驱动的 poll/tick/watch_* 编排。

    窗口/菜单/前台/提示音分别委派 platform/mac 的 PetWindow/PetMenu/ForegroundWatch/notify。
    """

    def __init__(self):
        self.settings = load_settings()
        self.state, self.text, self.project = 'waiting', '我来啦～', ''
        self.state_since = time.time()
        self.last_mtime = 0
        self.last_mtime_seen = 0
        self.hop_at = time.time()
        self.hidden = False
        self.error_streak = 0  # 连续 error 计数（石化彩蛋）
        self.last_alive = time.time()
        self.focus_watch = focus.ForegroundWatch()

        self.window = mac_window.PetWindow(self, os.path.join(HERE, 'sprites'), RUN_DIR)
        self.view = self.window.view
        self.menu = PetMenu(self)

    # ---------- 平台委派 ----------
    def refresh(self):
        self.window.refresh()

    def save_position(self, x, y):
        self.settings['x'], self.settings['y'] = x, y
        save_settings(self.settings)

    def show_menu(self, point):
        self.menu.popup(self.view, point)

    def bring_claude_front(self):
        focus.bring_claude_front()

    def claude_is_foreground(self):
        return self.focus_watch.claude_is_foreground()

    # ---------- 菜单动作（NSMenuItem target 是 view，转发回来）----------
    def setSize_(self, sender):
        name = sender.title()
        self.settings['size'] = name
        save_settings(self.settings)
        self.menu.update_size_state(name)
        self.window.resize()

    def toggleHide_(self, sender):
        sender.setState_(0 if sender.state() else 1)
        self.settings['hideOnFocus'] = bool(sender.state())
        save_settings(self.settings)

    def toggleSound_(self, sender):
        sender.setState_(0 if sender.state() else 1)
        self.settings['sound'] = bool(sender.state())
        save_settings(self.settings)

    def quit_(self, sender):
        NSApplication.sharedApplication().terminate_(None)

    # ---------- 状态 ----------
    def display_text(self):
        return core_view_model.display_text_with_dots(
            self.state, self.text, time.time(), self.state_since)

    def effective_state(self):
        return core_view_model.effective_state(self.state, self.state_since, time.time())

    def poll(self):
        # 坏状态文件不能冻住画面：出错了这一帧不画，下一帧继续
        try:
            self.poll_once()
        except Exception:
            core_errors.log_exception(RUN_DIR)
        finally:
            self.refresh()

    def poll_once(self):
        latest = read_latest()
        if latest and latest[0] != self.last_mtime:
            self.last_mtime_seen, self.last_mtime = self.last_mtime, latest[0]
            mapped = core_view_model.normalize(latest[1])
            changed = mapped.state != self.state
            self.state, self.text = mapped.state, mapped.text
            self.project = mapped.project
            self.state_since = time.time()
            # 石化彩蛋（协议 §3）：连续 3 次 error 由渲染层自己触发
            if mapped.state == 'error':
                self.error_streak += 1
                if self.error_streak >= 3:
                    self.state, self.text = 'stone', '石化了…'
            else:
                self.error_streak = 0
            if mapped.sound and self.settings.get('sound', True) and self.last_mtime_seen:
                play_sound(os.path.join(SOUNDS, mapped.sound + '.wav'))
            if changed:
                self.hop_at = time.time()

    def tick(self):
        # 33ms 动画帧 + “思考中”点点点
        self.refresh()

    def watch_focus(self):
        should_hide = (self.settings.get('hideOnFocus')
                       and self.claude_is_foreground()
                       and self.view.drag0 is None)
        if should_hide and not self.hidden:
            self.window.hide()
            self.hidden = True
        elif not should_hide and self.hidden:
            self.window.show()
            self.hidden = False

    def watch_claude(self):
        # Claude 关掉两分钟后，桌宠也自己退出
        if focus.claude_pids():
            self.last_alive = time.time()
        elif time.time() - self.last_alive > 120:
            NSApplication.sharedApplication().terminate_(None)
            return


def shoot(pet, path):
    """--shot：画几帧后把窗口存成 PNG 并退出（抓自己不用屏幕录制权限）。"""
    pet.window.capture(path)
    NSApplication.sharedApplication().terminate_(None)


def main():
    acquire_lock()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # 不占 Dock
    pet = Pet()
    if SHOT_PATH is not None:  # --shot <路径>：画几帧后截图退出
        if not SHOT_PATH:
            sys.exit('--shot 需要一个输出路径，例如：pet_mac.py --shot /tmp/pet.png')
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(1.5, False,
                                                              lambda t: shoot(pet, SHOT_PATH))
    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.25, True, lambda t: pet.poll())
    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.033, True, lambda t: pet.tick())
    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.3, True, lambda t: pet.watch_focus())
    NSTimer.scheduledTimerWithTimeInterval_repeats_block_(30, True, lambda t: pet.watch_claude())
    app.run()


def write_error_log():
    """把异常写进运行目录；目录不可写时至少别把原始异常吞掉。"""
    core_errors.log_exception(RUN_DIR)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        write_error_log()
