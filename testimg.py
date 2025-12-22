import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# 设置中文字体，避免中文显示乱码
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'sans-serif']

# 定义特征名称和两类网站的特征均值
features = ['URL长度', '域名注册时长', 'HTTPS状态得分']
legit_means = [42.5, 1250.6, 0.92]
phishing_means = [68.3, 105.2, -0.85]

# 设置X轴位置和柱状图宽度
x = np.arange(len(features))
width = 0.35

# 创建画布和坐标轴，设置尺寸
fig, ax = plt.subplots(figsize=(8, 5))
# 绘制合法网站柱状图
rects1 = ax.bar(x - width/2, legit_means, width, label='合法网站', color='skyblue')
# 绘制钓鱼网站柱状图
rects2 = ax.bar(x + width/2, phishing_means, width, label='钓鱼网站', color='lightcoral')

# 设置图表标签和标题
ax.set_ylabel('特征数值')
ax.set_title('合法网站与钓鱼网站关键特征对比')
ax.set_xticks(x)
ax.set_xticklabels(features)
ax.legend()

# 定义自动为柱状图添加数值标签的函数
def autolabel(rects):
    for rect in rects:
        height = rect.get_height()
        ax.annotate('{}'.format(height),
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3),  # 文字偏移量
                    textcoords="offset points",
                    ha='center', va='bottom')  # 水平/垂直对齐方式

# 为两类柱状图添加数值标签
autolabel(rects1)
autolabel(rects2)

# 自动调整布局，避免元素重叠
fig.tight_layout()
# 显示图表（本地运行必须加，Jupyter环境可省略）
plt.show()