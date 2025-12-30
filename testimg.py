import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
import matplotlib.font_manager as fm
import os

# 显示系统可用的中文字体
fontpaths = fm.findSystemFonts(fontpaths=None, fontext='ttf')
chinese_fonts = []
for fontpath in fontpaths:
    try:
        fontprop = fm.FontProperties(fname=fontpath)
        fontname = fontprop.get_name()
        if any(c in fontname for c in ['Hei', 'Heiti', 'Song', 'Kai', 'Fang', 'Microsoft', 'Sim', 'Noto', 'Arial Unicode']):
            chinese_fonts.append((fontname, fontpath))
    except:
        continue

print("系统可用的中文字体:")
for name, path in chinese_fonts:
    print(f"- {name}: {path}")

# 选择一个可用的中文字体 - 优先使用常见的中文字体
font_to_use = None
preferred_fonts = ['SimHei', 'Microsoft YaHei', 'SimSun', 'KaiTi', 'Arial Unicode MS', 'Noto Sans CJK SC']
for pref_font in preferred_fonts:
    for name, path in chinese_fonts:
        if pref_font in name or name in pref_font:
            font_to_use = name
            break
    if font_to_use:
        break

# 如果没有找到合适的中文字体，使用默认sans-serif
if not font_to_use:
    font_to_use = 'sans-serif'
    print("警告: 未找到合适的中文字体，将使用默认sans-serif字体")

print(f"将使用字体: {font_to_use}")

# 设置字体参数
plt.rcParams['font.sans-serif'] = [font_to_use] + plt.rcParams['font.sans-serif']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
sns.set_theme(style="whitegrid")

# 确保全局字体设置
plt.rcParams['font.family'] = 'sans-serif'

data = {
    '指标': ['流动比率', '流动比率', '流动比率', '速动比率', '速动比率', '速动比率', '现金比率', '现金比率', '现金比率'],
    '年份': ['2022中报', '2023中报', '2024中报', '2022中报', '2023中报', '2024中报', '2022中报', '2023中报', '2024中报'],
    '数值': [1.08, 1.15, 1.22, 0.73, 0.80, 0.85, 0.21, 0.25, 0.28],
    '类型': ['森麒麟'] * 9
}

industry_data = {
    '指标': ['流动比率', '速动比率', '现金比率'],
    '年份': ['行业平均', '行业平均', '行业平均'],
    '数值': [1.50, 1.10, 0.40],
    '类型': ['行业平均'] * 3
}

df = pd.DataFrame(data)
df_industry = pd.DataFrame(industry_data)
df_combined = pd.concat([df, df_industry], ignore_index=True)

fig, ax = plt.subplots(figsize=(12, 6))
sns.barplot(data=df_combined, x='指标', y='数值', hue='年份', palette='viridis', ax=ax)
ax.set_xlabel('偿债能力指标', fontsize=12)
ax.set_ylabel('比率值', fontsize=12)
ax.set_title('森麒麟短期偿债能力多年度对比与行业平均', fontsize=14, fontweight='bold')
ax.legend(title='年份')

# 重新设置刻度标签字体
for label in ax.get_xticklabels() + ax.get_yticklabels():
    label.set_fontproperties(fm.FontProperties(family=font_to_use))

# 重新设置标题和标签字体
ax.title.set_fontproperties(fm.FontProperties(family=font_to_use))
ax.xaxis.label.set_fontproperties(fm.FontProperties(family=font_to_use))
ax.yaxis.label.set_fontproperties(fm.FontProperties(family=font_to_use))

# 重新设置图例字体
legend = ax.legend(title='年份')
legend_title = legend.get_title()
legend_title.set_fontproperties(fm.FontProperties(family=font_to_use))
for text in legend.get_texts():
    text.set_fontproperties(fm.FontProperties(family=font_to_use))

plt.tight_layout()
plt.show()