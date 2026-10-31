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

    def test_unknown_state_falls_back_to_idle(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 's1', {'state': 'hacked', 'text': 'x'}, age=10)
        pet = make_pet()
        pet.poll()
        assert pet.state == 'idle'
        assert pet.text == 'x'  # 文本照常透传

    def test_missing_state_defaults_idle(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 's1', {'text': '只有文本'}, age=10)
        pet = make_pet()
        pet.poll()
        assert pet.state == 'idle'
        assert pet.text == '只有文本'

    def test_attention_state_applies(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 's1', {'state': 'attention', 'text': '需要你看一下'}, age=10)
        pet = make_pet()
        pet.poll()
        assert pet.state == 'attention'

    def test_aborted_reads_as_error(self, pet_state):
        petmod, _tmp, sessions = pet_state
        write_session(sessions, 's1', {'state': 'aborted', 'text': '被打断了…'}, age=10)
        pet = make_pet()
        pet.poll()
        assert (pet.state, pet.text) == ('error', '被打断了…')

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

    def test_three_consecutive_errors_trigger_stone(self, pet_state):
        """石化彩蛋（协议 §3）：连续 3 次 error 由渲染层触发，写入方只写 error。"""
        petmod, _tmp, sessions = pet_state
        pet = make_pet()
        for i in range(3):
            write_session(sessions, 's1', {'state': 'error', 'text': '出错了…'}, age=30 - i)
            pet.poll()
            time.sleep(0.01)
        assert (pet.state, pet.text) == ('stone', '石化了…')

    def test_stone_resets_on_non_error(self, pet_state):
        petmod, _tmp, sessions = pet_state
        pet = make_pet()
        for i in range(3):
            write_session(sessions, 's1', {'state': 'error', 'text': '出错了…'}, age=30 - i)
            pet.poll()
            time.sleep(0.01)
        assert pet.state == 'stone'
        write_session(sessions, 's1', {'state': 'thinking', 'text': '思考中'}, age=1)
        pet.poll()
        assert pet.state == 'thinking'
        assert pet.error_streak == 0


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
class TestNotifyGating:
    """#11：poll 路径上的原生通知——声音标记、勿扰、2 秒去重。"""

    def _record(self, petmod, monkeypatch):
        """记录原生通知调用；mac 记 (title, body, sound)，Windows 的 toast 无声参记 None。"""
        calls = []
        if pet_mac is not None and petmod is pet_mac:
            monkeypatch.setattr(petmod, 'notify', lambda t, b, sound=False: calls.append((t, b, sound)))
        else:
            monkeypatch.setattr(petmod, 'toast', lambda t, b: calls.append((t, b, None)))
            monkeypatch.setattr(petmod, 'flash_claude', lambda: None)
        return calls

    def test_attention_notifies_with_sound(self, pet_state, monkeypatch):
        petmod, _tmp, sessions = pet_state
        calls = self._record(petmod, monkeypatch)
        write_session(sessions, 's1', {'state': 'waiting', 'text': '', 'session': 's1'}, age=20)
        pet = make_pet()
        pet.poll()
        write_session(sessions, 's1',
                      {'state': 'attention', 'text': '需要你看一下', 'session': 's1'}, age=1)
        pet.poll()
        assert len(calls) == 1
        title, body, sound = calls[0]
        assert title == 'Claude 桌宠'
        assert '需要你看一下' in body and '双击桌宠' in body
        if pet_mac is not None and petmod is pet_mac:  # 声音标记只有 mac 横幅用
            assert sound is True

    def test_same_attention_twice_quickly_notifies_once(self, pet_state, monkeypatch):
        # 连续两次同样的 attention（中间隔个 thinking 让 changed 成立）2 秒内只弹一次
        petmod, _tmp, sessions = pet_state
        calls = self._record(petmod, monkeypatch)
        pet = make_pet()
        for i, state in enumerate(('attention', 'thinking', 'attention')):
            write_session(sessions, 's1',
                          {'state': state, 'text': '需要你看一下', 'session': 's1'},
                          age=30 - i * 10)
            pet.poll()
        assert len(calls) == 1

    def test_dnd_blocks_banner_and_chime(self, pet_state, monkeypatch):
        # 勿扰（#11）：不弹横幅也不播提示音；气泡状态照常更新
        petmod, _tmp, sessions = pet_state
        calls = self._record(petmod, monkeypatch)
        plays = []
        if pet_mac is not None and petmod is pet_mac:
            monkeypatch.setattr(petmod, 'play_sound', lambda p: plays.append(p))
        else:
            monkeypatch.setattr(petmod.winsound, 'PlaySound', lambda p, f: plays.append(p))
        write_session(sessions, 's1', {'state': 'waiting', 'text': '', 'session': 's1'}, age=20)
        pet = make_pet()
        pet.settings['dnd'] = True
        pet.poll()
        write_session(sessions, 's1',
                      {'state': 'celebrate', 'text': '搞定', 'sound': 'done', 'session': 's1'}, age=1)
        pet.poll()
        assert calls == [] and plays == []
        assert pet.state == 'celebrate'  # 气泡/表情不受勿扰影响

    def test_go_handle_failure_shows_project_path(self, pet_state, monkeypatch):
        # 菜单「去处理」找不到终端窗口时，气泡给出项目路径（#11）
        petmod, _tmp, _sessions = pet_state
        if pet_mac is not None and petmod is pet_mac:
            monkeypatch.setattr(petmod.focus, 'bring_claude_front', lambda: False)
            go = petmod.Pet.goHandle_
        else:
            monkeypatch.setattr(petmod, 'focus_claude', lambda: False)
            go = petmod.Pet.go_handle
        pet = make_pet()
        pet.project = 'demo'
        go(pet, None)
        assert 'demo' in pet.text


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
