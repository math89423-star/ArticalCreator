import matplotlib.pyplot as plt

import seaborn as sns

import pandas as pd



plt.rcParams['font.sans-serif'] = ['SimHei']

plt.rcParams['axes.unicode_minus'] = False

　　sns.set_theme(style="whitegrid")



　　data = {

　　'报告期': ['2020年年度', '2021年年度', '2022年年度', '2023年年度', '2024年Q1'],

　　'资产负债率(%)': [34.14, 36.27, 41.10, 42.30, 42.85]

　　}

　　df = pd.DataFrame(data)



plt.figure(figsize=(8, 5))

plt.plot(df['报告期'], df['资产负债率(%)'], marker='o', linewidth=2, markersize=8, color='#1f77b4')

plt.xlabel('报告期', fontsize=12)

plt.ylabel('资产负债率(%)', fontsize=12)

plt.title('森麒麟资产负债率变动趋势（2020-2024Q1）', fontsize=14)

plt.ylim(30, 50)

plt.grid(True, linestyle='--', alpha=0.7)



　　for i, rate in enumerate(df['资产负债率(%)']):

plt.annotate(f'{rate}%', (df['报告期'][i], rate), textcoords="offset points", xytext=(0,10), ha='center')