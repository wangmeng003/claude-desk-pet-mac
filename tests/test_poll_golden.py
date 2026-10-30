"""poll() 的状态映射与提示音门控锁定 —— sessions → view model 的核心行为。"""
import time

import pytest

from conftest import _VarStub, make_pet, pet_mac, pet_win, requires_platform, write_session


@requires_platform
class TestPollMapping:
    def test_applies_newest_state(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 's1', {'state': 'tool', 'text': '在跑命令…', 'project': 'demo'}, age=10)
        pet = make_pet()
        pet.poll()
        assert (pet.state, pet.text, pet.project) == ('tool', '在跑命令…', 'demo')

    def test_unknown_state_falls_back_to_waiting(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 's1', {'state': 'hacked', 'text': 'x'}, age=10)
        pet = make_pet()
        pet.poll()
        assert pet.state == 'waiting'
        assert pet.text == 'x'  # 文本照常透传

    def test_missing_state_defaults_waiting_empty_text(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 's1', {'text': '只有文本'}, age=10)
        pet = make_pet()
        pet.poll()
        assert pet.state == 'waiting'
        assert pet.text == '只有文本'

    def test_untouched_mtime_keeps_state(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 's1', {'state': 'tool', 'text': 't'}, age=10)
        pet = make_pet()
        pet.poll()
        since = pet.state_since
        time.sleep(0.01)
        pet.poll()  # 同一文件再 poll 一次
        assert pet.state == 'tool'
        assert pet.state_since == since  # 状态时间戳不被重置（发呆计时不受影响）


@requires_platform
class TestSoundGating:
    def _record_plays(self, petmod, monkeypatch):
        plays = []
        if pet_mac is not None and petmod is pet_mac:
            monkeypatch.setattr(petmod, 'play_sound', lambda p: plays.append(p))
        else:  # Windows: winsound.PlaySound
            monkeypatch.setattr(petmod.winsound, 'PlaySound',
                                lambda p, f: plays.append(p))
        return plays

    def test_first_poll_never_replays_old_sound(self, pet_state, monkeypatch):
        """last_mtime_seen 为 0（首次 poll）时，即使文件带 sound 也不播。"""
        petmod, _tmp, sessions = pet_state
        plays = self._record_plays(petmod, monkeypatch)
        write_session(sessions, 's1', {'state': 'waiting', 'text': '', 'sound': 'done'}, age=10)
        pet = make_pet()
        pet.poll()
        assert plays == []

    def test_second_poll_plays_done(self, pet_state, monkeypatch):
        petmod, _tmp, sessions = pet_state
        plays = self._record_plays(petmod, monkeypatch)
        write_session(sessions, 's1', {'state': 'waiting', 'text': ''}, age=20)
        pet = make_pet()
        pet.poll()
        write_session(sessions, 's1', {'state': 'celebrate', 'text': '搞定', 'sound': 'done'}, age=1)
        pet.poll()
        assert plays and plays[0].endswith('done.wav')

    def test_sound_disabled(self, pet_state, monkeypatch):
        petmod, _tmp, sessions = pet_state
        plays = self._record_plays(petmod, monkeypatch)
        write_session(sessions, 's1', {'state': 'waiting', 'text': ''}, age=20)
        pet = make_pet()
        # 平台差异（golden 锁定现状）：mac 版 poll 读 settings['sound']；
        # Windows 版读 sound_var（make_menu 时从 settings 初始化的 UI 状态）
        if pet_win is not None and petmod is pet_win:
            pet.sound_var = _VarStub(False)
        else:
            pet.settings['sound'] = False
        pet.poll()
        write_session(sessions, 's1', {'state': 'celebrate', 'text': '搞定', 'sound': 'done'}, age=1)
        pet.poll()
        assert plays == []

    def test_unknown_sound_value_ignored(self, pet_state, monkeypatch):
        petmod, _tmp, sessions = pet_state
        plays = self._record_plays(petmod, monkeypatch)
        write_session(sessions, 's1', {'state': 'waiting', 'text': ''}, age=20)
        pet = make_pet()
        pet.poll()
        write_session(sessions, 's1', {'state': 'error', 'text': '错', 'sound': 'hacked'}, age=1)
        pet.poll()
        assert plays == []


@requires_platform
class TestPollResilience:
    """poll 里出异常不能让轮询停摆，也不能把异常抛给调用方。"""

    def _boom(self, monkeypatch, petmod):
        def boom():
            raise RuntimeError('坏数据')
        monkeypatch.setattr(petmod.Pet, 'poll_once', boom)

    def test_poll_does_not_raise(self, pet_state, monkeypatch):
        petmod, _tmp, _sessions = pet_state
        pet = make_pet()
        self._boom(monkeypatch, petmod)
        pet.poll()  # 不能抛

    @pytest.mark.skipif(pet_win is None, reason='Windows 版 poll 用 root.after 续帧')
    def test_windows_poll_still_schedules_next_frame(self, pet_state, monkeypatch):
        """Windows：root.after 在最后，出错不续帧就永远停在旧表情。"""
        petmod, _tmp, _sessions = pet_state
        pet = make_pet()
        scheduled = []
        pet.root.after = lambda ms, cb: scheduled.append(cb)
        self._boom(monkeypatch, petmod)
        pet.poll()
        assert scheduled, 'poll 出错后没有排下一帧'

    @pytest.mark.skipif(pet_mac is None, reason='mac 版 poll 靠 refresh 刷新画面')
    def test_mac_poll_still_refreshes_after_error(self, pet_state, monkeypatch):
        """macOS：出错这一帧也要刷新，别把画面冻住。"""
        petmod, _tmp, _sessions = pet_state
        pet = make_pet()
        refreshed = []
        pet.refresh = lambda: refreshed.append(1)
        self._boom(monkeypatch, petmod)
        pet.poll()
        assert refreshed, 'poll 出错后没有刷新画面'
