---
name: ppt-chart-validator
description: PPT 图表坐标校验——验证 SVG 图表的数据-坐标映射是否准确。含图表数据提取和坐标校准指南。
version: 1.0.0
tags: [ppt, chart, validation, coordinates]
when_to_use: 生成包含图表的 PPT 页面后，检查图表坐标是否准确
allowed_tools: [read_slide, save_slide, calc_chart_positions]
required_tools: []
---

# 图表坐标校验

AI 生成图表时经常出现 10-50px 的坐标误差。本技能提供校验方法和修正指南。

---

## 常见图表坐标错误

### 柱状图 (bar_chart)
- 柱子高度与数据值不成比例
- 柱子间距不均匀
- Y 轴标签与刻度线不对齐

### 折线图 (line_chart)
- 数据点位置偏离实际值
- 折线连接点不在数据点中心
- 面积填充越界

### 饼图/环形图 (pie/donut_chart)
- 扇形角度与百分比不匹配
- 扇形之间有缝隙或重叠

### 雷达图 (radar_chart)
- 多边形顶点不在轴线上
- 轴线间距不均匀

## 校验方法

### 1. 数据-坐标映射检查

对于柱状图，验证：
```
柱子高度 = (数据值 / 最大值) * 图表区域高度
柱子 y 坐标 = 图表区域底部 - 柱子高度
```

对于折线图，验证：
```
数据点 y = 图表区域底部 - (数据值 - 最小值) / (最大值 - 最小值) * 图表区域高度
数据点 x = 起始 x + (索引 / (数据点数 - 1)) * 图表区域宽度
```

### 2. 布局一致性检查

- 所有柱子宽度相同
- 所有柱子间距相同
- 数据标签居中对齐
- 图例位置不遮挡数据

### 3. 视觉检查

- 坐标轴线是否可见
- 网格线是否过密或过疏
- 数据标签是否清晰可读

## 修正指南

1. 读取当前 SVG：`read_slide(N)`
2. 用 `calc_chart_positions` 工具计算正确坐标
3. 修正 SVG 中的坐标值
4. 用 `save_slide(N, svg="...")` 覆盖
5. 重新校验

## 支持的图表类型

| 类型 | 关键坐标 |
|------|---------|
| bar_chart | 柱子 x, y, width, height |
| line_chart | 数据点 cx, cy |
| pie_chart | 扇形 path d 属性 |
| radar_chart | 多边形 points 属性 |
| waterfall_chart | 柱子 y, height |
| gantt_chart | 条形 x, width |
