import matplotlib.pyplot as plt
import numpy as np
import matplotlib.font_manager as fm

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题

# 数据准备
years = [2020, 2021, 2022, 2023]
receivable_turnover_days = [62.33, 67.45, 71.28, 76.12]  # 应收账款周转天数
receivable_turnover_ratio = [5.78, 5.34, 5.05, 4.73]    # 应收账款周转率
receivable_amount = [8.51, 10.23, 12.67, 14.98]         # 应收账款净额（亿元）
revenue = [53.92, 58.41, 62.92, 78.42]                  # 营业总收入（亿元）

# 创建图表
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))

# 图1：应收账款周转天数趋势
ax1.plot(years, receivable_turnover_days, marker='o', linewidth=2, color='blue')
ax1.set_title('应收账款周转天数趋势（2020-2023）', fontsize=12)
ax1.set_xlabel('年份')
ax1.set_ylabel('周转天数')
ax1.grid(True, linestyle='--', alpha=0.7)

# 图2：应收账款周转率变化
ax2.plot(years, receivable_turnover_ratio, marker='s', color='red', linewidth=2)
ax2.set_title('应收账款周转率变化（2020-2023）', fontsize=12)
ax2.set_xlabel('年份')
ax2.set_ylabel('周转率（次）')
ax2.grid(True, linestyle='--', alpha=0.7)

# 图3：应收账款规模与营收对比
width = 0.35
x = np.arange(len(years))
ax3.bar(x - width/2, receivable_amount, width, label='应收账款净额', color='skyblue')
ax3.bar(x + width/2, revenue, width, label='营业总收入', color='salmon')
ax3.set_title('应收账款规模与营收对比（2020-2023）', fontsize=12)
ax3.set_xlabel('年份')
ax3.set_ylabel('金额（亿元）')
ax3.set_xticks(x)
ax3.set_xticklabels(years)
ax3.legend()
ax3.grid(True, linestyle='--', alpha=0.7)

# 图4：应收账款占流动资产比例
current_assets = [34.12, 38.45, 42.67, 59.92]  # 流动资产（亿元）
receivable_ratio = [round(receivable_amount[i]/current_assets[i]*100, 1) for i in range(len(years))]
ax4.plot(years, receivable_ratio, marker='^', color='green', linewidth=2)
ax4.set_title('应收账款占流动资产比例（2020-2023）', fontsize=12)
ax4.set_xlabel('年份')
ax4.set_ylabel('比例（%）')
ax4.grid(True, linestyle='--', alpha=0.7)

plt.tight_layout()
plt.show()