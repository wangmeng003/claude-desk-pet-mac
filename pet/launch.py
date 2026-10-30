# 把桌宠作为独立进程启动，然后立刻退出（mod 那边就不会被卡住）
# 用法：python launch.py <pet 脚本路径> <运行目录> [额外参数…]
import os
import subprocess
import sys

if len(sys.argv) < 3:
    sys.exit('用法：python launch.py <pet 脚本路径> <运行目录> [额外参数…]')

pet_script, run_dir = sys.argv[1], sys.argv[2]
extra = sys.argv[3:]  # 例如 --quiet（hooks 自动拉起时不弹单实例对话框）

if sys.platform == 'darwin':
    # macOS：start_new_session 让桌宠脱离 Claude 的进程组，会话结束后不被一起关掉
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, 'launch.log'), 'w', encoding='utf-8') as log:
        try:
            proc = subprocess.Popen([sys.executable, pet_script, run_dir, *extra],
                                    start_new_session=True, close_fds=True,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.write(f'启动成功 pid={proc.pid} python={sys.executable}\n')
        except OSError as err:
            log.write(f'失败：{err}\n')
    sys.exit(0)
pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
if not os.path.exists(pythonw):
    pythonw = sys.executable

DETACHED = 0x00000008
NEW_GROUP = 0x00000200
BREAKAWAY = 0x01000000  # 脱离 Claude 的作业对象，会话结束时桌宠不会被一起关掉

os.makedirs(run_dir, exist_ok=True)
with open(os.path.join(run_dir, 'launch.log'), 'w', encoding='utf-8') as log:
    log.write(f'python={sys.executable}\npythonw={pythonw}\n')
    for flags in (DETACHED | NEW_GROUP | BREAKAWAY, DETACHED | NEW_GROUP):
        try:
            proc = subprocess.Popen([pythonw, pet_script, run_dir, *extra], creationflags=flags, close_fds=True,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.write(f'启动成功 pid={proc.pid} flags={flags:#x}\n')
            break
        except OSError as err:
            log.write(f'flags={flags:#x} 失败：{err}\n')
