"""M3 多会话 poll 行为：气泡计数、按会话通知、pin 切换、不闪烁（specs §5.3）。

聚合器/气泡组合是纯函数（任何平台可跑）；poll 集成测试双平台同跑
（#23 起 Windows 也走聚合器），通知/声音记录按平台打桩。
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PET_DIR = REPO / 'pet'
if str(PET_DIR) not in sys.path:
    sys.path.insert(0, str(PET_DIR))


from conftest import make_pet, pet_mac, requires_platform, write_session  # noqa: E402
from core import aggregate, view_model  # noqa: E402


class TestBubbleText:
    def test_single_session_no_suffix(self):
        assert view_model.bubble_text('在改 x.ts', 1, 0) == '在改 x.ts'
        assert view_model.bubble_text('在改 x.ts', 1, 1) == '在改 x.ts'

    def test_multi_without_waiting(self):
        assert view_model.bubble_text('思考中', 3, 0) == '思考中 · 3 个会话'

    def test_multi_with_waiting(self):
        assert view_model.bubble_text('在改 register.ts', 3, 2) == '在改 register.ts · 3 个会话 · 2 个等你'


def record_notify(petmod, monkeypatch):
    """记录原生通知；mac 记 (title, body, sound)，Windows 的 Toast 无声参记 None。"""
    calls = []
    if pet_mac is not None and petmod is pet_mac:
        monkeypatch.setattr(petmod, 'notify', lambda t, b, sound=False: calls.append((t, b, sound)))
    else:
        monkeypatch.setattr(petmod, 'toast', lambda t, b: calls.append((t, b, None)))
        monkeypatch.setattr(petmod, 'flash_claude', lambda: None)
    return calls


def record_sound(petmod, monkeypatch):
    plays = []
    if pet_mac is not None and petmod is pet_mac:
        monkeypatch.setattr(petmod, 'play_sound', lambda p: plays.append(p))
    else:
        monkeypatch.setattr(petmod.winsound, 'PlaySound', lambda p, f: plays.append(p))
    return plays


def force_focus(petmod, monkeypatch, ok: bool):
    """打桩通用聚焦：mac 走 focus 模块，Windows 走 Pet.focus_claude。"""
    if pet_mac is not None and petmod is pet_mac:
        monkeypatch.setattr(petmod.focus, 'bring_claude_front', lambda: ok)
    else:
        monkeypatch.setattr(petmod.Pet, 'focus_claude', lambda self: ok)


@requires_platform
class TestPollMultiSession:
    def _write_three(self, sessions):
        """一个 working、一个 waiting、一个 error（M3 通过门槛场景）。"""
        write_session(sessions, 'work', {'state': 'tool', 'text': '在改 register.ts',
                                         'project': 'pet', 'session': 'work'}, age=5)
        write_session(sessions, 'wait', {'state': 'waiting', 'text': '轮到你啦！',
                                         'project': 'web', 'session': 'wait'}, age=4)
        write_session(sessions, 'boom', {'state': 'error', 'text': '出错了…',
                                         'project': 'api', 'session': 'boom'}, age=3)

    def test_bubble_shows_counts_and_priority_main(self, pet_state):
        petmod, _tmp, sessions = pet_state
        self._write_three(sessions)
        pet = make_pet()
        pet.poll()
        assert pet.state == 'error'          # error(80) > waiting(70) > tool(40)
        assert pet.project == 'api'
        assert pet.display_text() == '出错了… · 3 个会话 · 2 个等你'

    def test_consecutive_polls_do_not_flicker(self, pet_state):
        """不闪烁（通过门槛）：同一批文件连续 poll，主会话/文案/计时全部稳定。"""
        petmod, _tmp, sessions = pet_state
        self._write_three(sessions)
        pet = make_pet()
        pet.poll()
        first_text, since = pet.display_text(), pet.state_since
        pet.poll()
        pet.poll()
        assert pet.display_text() == first_text
        assert pet.state_since == since

    def test_background_error_notifies_while_main_unchanged(self, pet_state, monkeypatch):
        """后台会话出错也要通知（不丢），主会话不被抢（#21/#23 核心）。"""
        petmod, _tmp, sessions = pet_state
        calls = record_notify(petmod, monkeypatch)
        write_session(sessions, 'hot', {'state': 'attention', 'text': '需要你看一下',
                                        'project': 'a', 'session': 'hot'}, age=10)
        write_session(sessions, 'bg', {'state': 'thinking', 'text': '思考中',
                                       'project': 'b', 'session': 'bg'}, age=9)
        pet = make_pet()
        pet.poll()
        assert pet.state == 'attention'
        assert len(calls) == 1  # 首见即迁移：attention 上桌就通知一次
        calls.clear()
        write_session(sessions, 'bg', {'state': 'error', 'text': '出错了…',
                                       'project': 'b', 'session': 'bg'}, age=1)
        pet.poll()
        assert pet.state == 'attention'  # 主会话不被后台 error 抢
        assert len(calls) == 1           # 但后台 error 的通知照发
        assert '出错了' in calls[0][1]

    def test_pinned_session_wins_until_expired(self, pet_state):
        petmod, _tmp, sessions = pet_state
        self._write_three(sessions)
        pet = make_pet()
        pet.poll()
        assert pet.state == 'error'
        pet.pinned = 'work'
        pet.poll()
        assert pet.state == 'tool' and pet.project == 'pet'  # pin 胜过优先级
        # 被 pin 的会话过期（tool TTL 30 分钟）：自动解除，回聚合主会话
        write_session(sessions, 'work', {'state': 'tool', 'text': '在改 register.ts',
                                         'project': 'pet', 'session': 'work'}, age=31 * 60)
        pet.poll()
        assert pet.pinned == ''
        assert pet.state == 'error'

    def test_single_sound_per_frame_picks_top(self, pet_state, monkeypatch):
        """两个会话同帧带声音：只播优先级最高的一条，不叠音。"""
        petmod, _tmp, sessions = pet_state
        plays = record_sound(petmod, monkeypatch)
        write_session(sessions, 'a', {'state': 'waiting', 'text': '',
                                      'project': 'a', 'session': 'a'}, age=20)
        write_session(sessions, 'b', {'state': 'waiting', 'text': '',
                                      'project': 'b', 'session': 'b'}, age=19)
        pet = make_pet()
        pet.poll()  # 首见不播
        write_session(sessions, 'a', {'state': 'error', 'text': '错', 'sound': 'error',
                                      'project': 'a', 'session': 'a'}, age=2)
        write_session(sessions, 'b', {'state': 'celebrate', 'text': '好', 'sound': 'done',
                                      'project': 'b', 'session': 'b'}, age=1)
        pet.poll()
        assert len(plays) == 1 and plays[0].endswith('error.wav')  # error > celebrate

    def test_stone_only_for_main_session(self, pet_state):
        """后台会话连错 3 次不石化主会话（彩蛋按会话记账，只上主会话的屏）。"""
        petmod, _tmp, sessions = pet_state
        # 主会话用 attention(90)：压得过 error(80)，后台连错也抢不走主位
        write_session(sessions, 'main', {'state': 'attention', 'text': '需要你看一下',
                                         'project': 'a', 'session': 'main'}, age=100)
        pet = make_pet()
        pet.poll()
        for i in range(3):
            write_session(sessions, 'bg', {'state': 'error', 'text': '出错了…',
                                           'project': 'b', 'session': 'bg'}, age=50 - i)
            pet.poll()
            time.sleep(0.01)
        assert pet.state == 'attention'  # bg 连击 3 次只记账，不把主会话石化


class TestSessionMenu:
    """#22/#23：菜单会话区数据（纯函数）——平台层只画 NSMenu/tkinter，不拼文案不排序。"""

    def _state(self, state, ts, session='s', project='p', attention=None):
        data = {'state': state, 'session': session, 'ts': ts, 'project': project}
        if attention is not None:
            data['attention'] = attention
        return view_model.normalize(data)

    def test_minutes_ago_buckets(self):
        now = 100000.0
        assert view_model.minutes_ago(now - 30, now) == '刚刚'
        assert view_model.minutes_ago(now - 5 * 60, now) == '5 分钟前'
        assert view_model.minutes_ago(now - 90 * 60, now) == '1 小时 30 分前'
        assert view_model.minutes_ago(now - 2 * 3600, now) == '2 小时前'

    def test_label_uses_project_state_and_age(self):
        now = 100000.0
        s = self._state('tool', now - 5 * 60, project='pet')
        assert view_model.session_label(s, now) == 'pet · 在跑工具 · 5 分钟前'

    def test_label_privacy_falls_back_to_short_id(self):
        now = 100000.0
        s = self._state('waiting', now - 60, session='abc12345', project='')
        assert view_model.session_label(s, now) == '会话 2345 · 等你 · 1 分钟前'

    def test_entries_sorted_by_priority_with_checkmark(self):
        now = 100000.0
        states = [
            self._state('tool', now - 10, 'work', 'pet'),
            self._state('error', now - 20, 'boom', 'api'),
            self._state('attention', now - 30, 'hot', 'web'),
        ]
        entries = aggregate.session_entries(states, main_session='boom', now=now)
        assert [e[1] for e in entries] == ['hot', 'boom', 'work']  # 按优先级倒序
        assert [e[2] for e in entries] == [False, True, False]     # 主会话打勾

    def test_entries_empty(self):
        assert aggregate.session_entries([], '', now=0.0) == []


@requires_platform
class TestPickSession:
    """#22/#23：菜单点击 → pin + 通用聚焦。"""

    class _Item:
        """mac 的 NSMenuItem 替身（representedObject 带 session id）。"""

        def __init__(self, sid):
            self._sid = sid

        def representedObject(self):
            return self._sid

    def _pick(self, pet, petmod, sid):
        if pet_mac is not None and petmod is pet_mac:
            pet.pickSession_(self._Item(sid))
        else:
            pet.pick_session(sid)

    def test_pick_pins_and_polls_immediately(self, pet_state, monkeypatch):
        petmod, _tmp, sessions = pet_state
        force_focus(petmod, monkeypatch, ok=True)
        write_session(sessions, 'hot', {'state': 'attention', 'text': '需要你看一下',
                                        'project': 'a', 'session': 'hot'}, age=3)
        write_session(sessions, 'work', {'state': 'tool', 'text': '在改 x.ts',
                                         'project': 'b', 'session': 'work'}, age=2)
        pet = make_pet()
        pet.poll()
        assert pet.state == 'attention'
        self._pick(pet, petmod, 'work')
        assert pet.pinned == 'work'
        assert pet.state == 'tool' and pet.project == 'b'  # poll 已立即生效

    def test_pick_unknown_session_ignored(self, pet_state, monkeypatch):
        petmod, _tmp, sessions = pet_state
        force_focus(petmod, monkeypatch, ok=True)
        write_session(sessions, 'work', {'state': 'tool', 'text': '在改 x.ts',
                                         'project': 'b', 'session': 'work'}, age=2)
        pet = make_pet()
        pet.poll()
        self._pick(pet, petmod, 'ghost')
        assert pet.pinned == ''

    def test_pick_focus_failure_shows_project_path(self, pet_state, monkeypatch):
        petmod, _tmp, sessions = pet_state
        force_focus(petmod, monkeypatch, ok=False)
        write_session(sessions, 'work', {'state': 'tool', 'text': '在改 x.ts',
                                         'project': 'b', 'session': 'work'}, age=2)
        pet = make_pet()
        pet.poll()
        self._pick(pet, petmod, 'work')
        assert '没找到终端窗口' in pet.text and 'b' in pet.text
