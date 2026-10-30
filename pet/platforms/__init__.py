# pet/platforms：各平台原生实现（mac: AppKit；后续 windows: tkinter/winsound）。
# 名字用复数 platforms：与标准库 platform 同名会在 pet/ 位于 sys.path[0] 时
# 遮蔽标准库模块（pytest 启动即缓存它），这里不冒这个险。
