"""M3 #21 多会话 poll 行为：气泡计数、按会话通知、pin 切换、不闪烁（specs §5.3）。

聚合器/气泡组合是纯函数（任何平台可跑）；poll 集成测试走 mac 路径——
Windows pet.pyw 在 #23 接入聚合器前仍是旧的 mtime 路径。
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PET_DIR = REPO / 'pet'
if str(PET_DIR) not in sys.path:
    sys.path.insert(0, str(PET_DIR))

import pytest  # noqa: E402

from conftest import make_pet, pet_mac, write_session  # noqa: E402
from core import view_model  # noqa: E402

mac_only = pytest.mark.skipif(pet_mac is None, reason='M3 #23：Windows 未接聚合器')


class TestBubbleText:
    def test_single_session_no_suffix(self):
        assert view_model.bubble_text('在改 x.ts', 1, 0) == '在改 x.ts'
        assert view_model.bubble_text('在改 x.ts', 1, 1) == '在改 x.ts'

    def test_multi_without_waiting(self):
        assert view_model.bubble_text('思考中', 3, 0) == '思考中 · 3 个会话'

    def test_multi_with_waiting(self):
        assert view_model.bubble_text('在改 register.ts', 3, 2) == '在改 register.ts · 3 个会话 · 2 个等你'


@mac_only
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
        """后台会话出错也要通知（不丢），主会话不被抢（#21 核心）。"""
        petmod, _tmp, sessions = pet_state
        calls = []
        monkeypatch.setattr(petmod, 'notify',
                            lambda t, b, sound=False: calls.append((t, b, sound)))
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
        plays = []
        monkeypatch.setattr(petmod, 'play_sound', lambda p: plays.append(p))
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
