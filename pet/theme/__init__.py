# theme：主题包（M4，specs/theme.md）。feature 模块——core 不认识主题，渲染层从这里拿皮肤。
# 只允许 stdlib：校验用魔数字节 + 头部尺寸，完整解码交给渲染层的 PIL（坏图走渲染层回退）。
