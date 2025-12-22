# import matplotlib.pyplot as plt
# import pandas as pd
# import numpy as np

# # 设置中文字体，避免中文显示乱码（虽然标题是英文，保留该配置更通用）
# plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'sans-serif']

# # 定义评估指标、模型名称和对应的性能数据
# metrics = ['Accuracy', 'Precision', 'Recall', 'F1-Score', 'AUC']
# models = ['Logistic Regression', 'Random Forest', 'XGBoost', 'CNN']

# data = {
# 'Logistic Regression': [0.92, 0.89, 0.87, 0.88, 0.94],
# 'Random Forest': [0.96, 0.94, 0.91, 0.925, 0.98],
# 'XGBoost': [0.97, 0.95, 0.93, 0.94, 0.985],
# 'CNN': [0.98, 0.96, 0.95, 0.955, 0.99]
# }

# # 计算雷达图的角度（闭合雷达图需要首尾相连）
# angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
# angles += angles[:1]# 追加第一个角度，让雷达图闭合

# # 创建极坐标子图，设置画布尺寸
# fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))

# # 遍历每个模型，绘制对应的雷达图曲线并填充
# for model in models:
# values = data[model]
# values += values[:1]# 追加第一个数值，让曲线闭合
# ax.plot(angles, values, 'o-', linewidth=2, label=model)
# ax.fill(angles, values, alpha=0.1)# 填充区域，透明度0.1

# # 配置雷达图样式
# ax.set_yticklabels([])# 隐藏径向刻度标签（避免数值重叠）
# ax.set_xticks(angles[:-1])# 设置角度刻度（去掉最后一个重复的角度）
# ax.set_xticklabels(metrics)# 角度刻度对应评估指标
# ax.set_title('Model Performance Comparison on Phishing Detection', size=14, pad=20)# 图表标题
# ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0))# 图例位置调整

# # 自动调整布局，避免元素重叠
# plt.tight_layout()
# # 显示图表（本地运行必须添加，Jupyter环境可省略）
# plt.show()


import matplotlib.pyplot as plt

import pandas as pd

import numpy as np



plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'sans-serif']



metrics = ['Accuracy', 'Precision', 'Recall', 'F1-Score', 'AUC']

models = ['Logistic Regression', 'Random Forest', 'XGBoost', 'CNN']



data = {

'Logistic Regression': [0.92, 0.89, 0.87, 0.88, 0.94],

'Random Forest': [0.96, 0.94, 0.91, 0.925, 0.98],

'XGBoost': [0.97, 0.95, 0.93, 0.94, 0.985],

'CNN': [0.98, 0.96, 0.95, 0.955, 0.99]

}



angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()

angles += angles[:1]



fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))

for model in models:
    values = data[model]
    values += values[:1]
    ax.plot(angles, values, 'o-', linewidth=2, label=model)
    ax.fill(angles, values, alpha=0.1)



ax.set_yticklabels([])

ax.set_xticks(angles[:-1])

ax.set_xticklabels(metrics)

ax.set_title('Model Performance Comparison on Phishing Detection', size=14, pad=20)

ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0))

plt.tight_layout()
plt.show()