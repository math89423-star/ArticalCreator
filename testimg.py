import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from matplotlib.font_manager import FontProperties  # 导入字体管理工具

# ========== 强制绑定Windows系统SimHei字体（彻底解决中文方框） ==========
# 直接指定SimHei字体文件路径（Windows系统默认路径）
font = FontProperties(fname=r'C:\Windows\Fonts\simhei.ttf', size=12)
# 全局配置+显式字体双保险
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示异常
# ==================================================================

sns.set_theme(style="whitegrid")

# 构建数据（修正全角空格，统一缩进）
data = {
    '年份': ['2022', '2023', '2024'],
    '营业总收入（亿元）': [62.92, 78.42, 85.11],
    '归属净利润（亿元）': [8.01, 13.69, 21.86]
}
df = pd.DataFrame(data)

# 创建画布和主坐标轴
fig, ax1 = plt.subplots(figsize=(10, 6))
# 绘制营业总收入折线（显式指定字体）
ax1.plot(df['年份'], df['营业总收入（亿元）'], marker='o', linewidth=2, label='营业总收入', color='#1f77b4')
ax1.set_xlabel('年份', fontproperties=font, fontsize=12)  # 绑定字体
ax1.set_ylabel('营业总收入（亿元）', fontproperties=font, fontsize=12, color='#1f77b4')  # 绑定字体
ax1.tick_params(axis='y', labelcolor='#1f77b4')

# 创建次坐标轴
ax2 = ax1.twinx()
# 绘制归属净利润折线（显式指定字体）
ax2.plot(df['年份'], df['归属净利润（亿元）'], marker='s', linewidth=2, label='归属净利润', color='#d62728')
ax2.set_ylabel('归属净利润（亿元）', fontproperties=font, fontsize=12, color='#d62728')  # 绑定字体
ax2.tick_params(axis='y', labelcolor='#d62728')

# 设置标题（显式指定字体）
plt.title('森麒麟2022-2024年营收与净利润趋势', fontproperties=font, fontsize=14, pad=20)  # 绑定字体
# 设置图例（显式指定字体）
ax1.legend(prop=font, loc='upper left')  # 图例绑定字体
ax2.legend(prop=font, loc='upper right')  # 图例绑定字体

plt.tight_layout()
plt.show()