# Claude 娘桌宠悬浮窗 · macOS 版
# 本文件是 composition root：组装 settings / core / platform，平台细节都在 platform/mac/。
# 状态文件、设置文件和 Windows 版 pet.pyw 保持同一套约定。
# 用法：python pet_mac.py <运行目录>
import atexit
import os
import queue
import signal
import subprocess
import sys
import time

from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSEvent,
                    NSEventTypeApplicationDefined, NSMakePoint)
from Foundation import NSTimer

from core import cli_args
from core import errors as core_errors
from core import lock
from core import sessions as core_sessions
from core import state_reader as core_state_reader
from core import view_model as core_view_model
from core.models import IDLE_AFTER, SIZES, SPRITES  # noqa: F401  (测试从入口锁定契约)
from platforms.mac import focus
from platforms.mac import card as mac_card
from platforms.mac import window as mac_window
from platforms.mac.menu import PetMenu
from platforms.mac.notify import notify, play_sound

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS = os.path.join(os.path.dirname(HERE), 'sounds')
# --shot <路径> 里的路径是截图输出位置，不是运行目录
RUN_DIR, SHOT_PATH = cli_args.parse_args(sys.argv[1:], cli_args.default_run_dir())
SESSIONS = os.path.join(RUN_DIR, 'sessions')
SETTINGS = os.path.join(RUN_DIR, 'settings.json')
QUIET = '--quiet' in sys.argv[1:]  # 被 hooks 自动拉起：单实例冲突只写日志，不弹对话框

# 只允许开一个桌宠：占住一个本地端口，占不到说明已经有一个在跑
# （在 acquire_lock() 里做，保持 import 本模块无副作用，测试才能导入）
_lock = None


def quit_app():
    """所有退出路径的统一入口：让 app.run() 返回，main() 的 finally 才有机会停桥。

    stop: 只在处理完「下一个事件」后生效，无事件时 run loop 永远等下去（macOS 27
    上实测如此）——补发一个空事件把它唤醒。terminate_ 走 exit(0)，finally 不会执行，
    bridge.json 会泄漏、pending 请求没人回，不能用。
    """
    app = NSApplication.sharedApplication()
    app.stop_(None)
    ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_characters_charactersIgnoringModifiers_isARepeat_keyCode_(
        NSEventTypeApplicationDefined, NSMakePoint(0, 0), 0, 0.0, 0, None, '', '', False, 0)
    app.postEvent_atStart_(ev, True)


def report_and_exit(msg, code, quiet):
    """单实例冲突的明确提示（#5）：写 pet-error.log；手动启动再弹对话框。"""
    try:
        with open(os.path.join(RUN_DIR, 'pet-error.log'), 'a', encoding='utf-8') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} 单实例锁：{msg}\n')
    except OSError:
        pass
    if not quiet:
        subprocess.run(['/usr/bin/osascript', '-e',
                        f'display dialog "{msg}" buttons {{"好"}} default button 1 with icon caution'])
    sys.exit(code)


def acquire_lock(quiet):
    global _lock
    kind, info = lock.acquire(RUN_DIR, lock.port_from_env())
    if kind == 'acquired':
        _lock = info  # 一直持有：GC/关闭都会放开端口，第二只桌宠就能进来
        atexit.register(lock.remove_lock, lock.lock_path(RUN_DIR))
    elif kind == 'another-pet':
        report_and_exit(f'已经有一只桌宠在跑啦（PID {info["pid"]}），就不再开第二只。', 0, quiet)
    else:
        report_and_exit(
            f'端口 {info["port"]} 被其他程序占用，桌宠起不来。'
            f'设置环境变量 PET_PORT 换一个端口（例如 47400）再启动。', 1, quiet)


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
        self.notify_gate = core_view_model.NotifyGate()
        self.focus_watch = focus.ForegroundWatch()
        self.bridge = None  # main() 里 attach_bridge 后才有（#15）
        self.card_events = queue.SimpleQueue()  # HTTP 线程 → 主线程（只传事件，不碰 AppKit）
        self.card = None

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
        return focus.bring_claude_front()

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

    def togglePrivacy_(self, sender):
        # 隐私模式（#8）：状态文件不写项目名/文件名；hooks 一分钟内重读到开关
        sender.setState_(0 if sender.state() else 1)
        self.settings['privacy'] = bool(sender.state())
        save_settings(self.settings)

    def toggleNotify_(self, sender):
        # 原生通知开关（#6）：celebrate/error/attention 三类状态弹系统通知
        sender.setState_(0 if sender.state() else 1)
        self.settings['notify'] = bool(sender.state())
        save_settings(self.settings)

    def toggleDnd_(self, sender):
        # 勿扰模式（#11）：不弹横幅不响铃，气泡/表情照常
        sender.setState_(0 if sender.state() else 1)
        self.settings['dnd'] = bool(sender.state())
        save_settings(self.settings)

    def goHandle_(self, sender):
        # 菜单「去处理」（#11）：聚焦终端；找不到窗口时气泡给出项目路径
        if not focus.bring_claude_front():
            self.text = (f'没找到终端窗口，项目在 {self.project}'
                         if self.project else '没找到终端窗口')
            self.state_since = time.time()

    def quit_(self, sender):
        quit_app()

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
            self.drain_card_events()
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
            if (mapped.sound and self.settings.get('sound', True)
                    and not self.settings.get('dnd') and self.last_mtime_seen):
                play_sound(os.path.join(SOUNDS, mapped.sound + '.wav'))
            # 原生通知（#6/#11）：长任务完成/出错/需要你看，状态切换时弹一次；
            # 勿扰不弹不响、同一件事 2 秒内只弹一次、attention 自带铃声
            if self.notify_gate.allow(mapped.state, mapped.text, mapped.session,
                                      changed, self.settings, time.time()):
                notify('Claude 桌宠',
                       core_view_model.notify_body(mapped.text, mapped.project,
                                                   bool(self.settings.get('privacy'))),
                       sound=core_view_model.notify_sound(mapped.state))
            if changed:
                self.hop_at = time.time()

    def tick(self):
        # 33ms 动画帧 + “思考中”点点点 + 卡片倒计时
        if self.card is not None:
            self.card.tick(time.time())
        self.refresh()

    # ---------- 权限审批卡片（#15）----------
    def attach_bridge(self, server) -> None:
        """main() 起桥后注入；测试不调它就整条链路静默关闭。"""
        self.bridge = server

    def permission_incoming(self, vm) -> None:
        """bridge on_request 回调（HTTP 线程）：只入队，AppKit 只在主线程碰。"""
        self.card_events.put(('request', vm))

    def permission_settled(self, rid: str, decision: str, reason: str) -> None:
        """bridge on_settled 回调（HTTP 线程）：桥侧已结束（超时/退出），关匹配的卡片。"""
        self.card_events.put(('settled', rid))

    def drain_card_events(self) -> None:
        if self.bridge is None:
            return
        while True:
            try:
                kind, payload = self.card_events.get_nowait()
            except queue.Empty:
                return
            if kind == 'request':
                if self.card is None:  # 忙时 bridge 已 409，不会到这；防御只弹一张
                    self.card = mac_card.PermissionCard(
                        self, payload, time.time() + core_view_model.CARD_TIMEOUT)
                    self.card.show(self._card_origin())
            elif self.card is not None and self.card.settle_if_matching(payload):
                self.card = None

    def permission_decide(self, rid: str, decision: str, reason: str = 'user') -> None:
        """卡片按钮/关窗 → 桥的决策；卡片自己已关。"""
        self.card = None
        if self.bridge is not None:
            self.bridge.decide(rid, decision, reason)

    def _card_origin(self):
        """卡片落在宠物上方；窗口不在（测试形态）就给 None 用默认位置。"""
        try:
            f = self.window.win.frame()
            return (f.origin.x, f.origin.y + f.size.height + 8)
        except Exception:
            return None

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

    def watch_lifecycle(self):
        # 没有活跃会话（ts+TTL 判定，#4）超过两分钟，桌宠自己退出。
        # 不再靠 pgrep claude：Windows 终端里的 Claude 找不到 claude.exe 会误退。
        if core_sessions.has_live_session(SESSIONS):
            self.last_alive = time.time()
        elif time.time() - self.last_alive > 120:
            quit_app()  # 也走 run() 返回路径：finally 停桥再退
            return


def shoot(pet, path):
    """--shot：画几帧后把窗口存成 PNG 并退出（抓自己不用屏幕录制权限）。"""
    pet.window.capture(path)
    NSApplication.sharedApplication().terminate_(None)


def main():
    if SHOT_PATH is None:  # --shot 是诊断/测试路径，不参与抢锁
        acquire_lock(QUIET)
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # 不占 Dock
    pet = Pet()
    server = None
    if SHOT_PATH is None:  # 审批桥随真桌宠起停（#13/#15）；--shot 诊断路径不起桥
        from bridge.server import BridgeServer
        server = BridgeServer(RUN_DIR, on_request=pet.permission_incoming,
                              on_settled=pet.permission_settled)
        server.start()
        pet.attach_bridge(server)
    try:
        # SIGTERM 走正常退出路径：run() 返回 → finally 停桥（pending 转 ask + 删 bridge.json）
        signal.signal(signal.SIGTERM, lambda _s, _f: quit_app())
        if SHOT_PATH is not None:  # --shot <路径>：画几帧后截图退出
            if not SHOT_PATH:
                sys.exit('--shot 需要一个输出路径，例如：pet_mac.py --shot /tmp/pet.png')
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(1.5, False,
                                                                  lambda t: shoot(pet, SHOT_PATH))
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.25, True, lambda t: pet.poll())
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.033, True, lambda t: pet.tick())
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.3, True, lambda t: pet.watch_focus())
        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(30, True, lambda t: pet.watch_lifecycle())
        app.run()
    finally:
        if server is not None:
            server.stop()  # pending 全转 ask + 删 bridge.json（#13）


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
