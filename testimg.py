import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from matplotlib.font_manager import FontProperties

# Ensure the font path is correct for the execution environment.
# For example, on a standard Windows machine:
# font_path = r'C:\Windows\Fonts\simhei.ttf'
# On a Linux system, you might need to specify a path like:
# font_path = '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'
# This example uses a common Windows path.
font = None  # 先初始化font变量，避免未定义报错
try:
    # 加载本地黑体字体文件，使用半角缩进
    font = FontProperties(fname=r'C:\Windows\Fonts\simhei.ttf', size=12)
except FileNotFoundError:
    # A fallback for environments where SimHei is not in the default path
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
    # 兜底初始化font，使用全局配置的字体
    font = FontProperties(size=12)

# 解决负号显示异常问题
plt.rcParams['axes.unicode_minus'] = False
sns.set_theme(style="whitegrid")

# Data representing the perceived severity of challenges (illustrative scores out of 10)
data = {
    '挑战维度': ['国际法规复杂性', '合规成本高昂', '复合人才短缺', '技术实现难度'],
    '挑战严峻指数': [9.2, 8.7, 7.9, 6.5]
}
df = pd.DataFrame(data)

plt.figure(figsize=(8, 5))
bar_plot = sns.barplot(x='挑战严峻指数', y='挑战维度', data=df, palette='viridis', orient='h')

# 设置坐标轴标签字体
plt.xlabel('挑战严峻指数 (评估分)', fontproperties=font)
plt.ylabel('挑战维度', fontproperties=font)
plt.title('苏州跨境电商企业数据合规挑战维度评估', fontproperties=font, fontsize=14)

# Set font for tick labels（修正缩进，使用半角空格）
for label in plt.gca().get_xticklabels() + plt.gca().get_yticklabels():
    label.set_fontproperties(font)

plt.tight_layout()
plt.show()  # 可选：添加显示图表的语句