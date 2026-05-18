from wuwei.tools import ToolRegistry


def register_chart_tools(registry: ToolRegistry) -> None:
    @registry.tool(display_name="计算图表坐标")
    async def calc_chart_positions(
        chart_type: str,
        data: str,
        format: str = "ppt169",
        bar_width: float | None = None,
        gap_ratio: float = 0.3,
        horizontal: bool = False,
        center: str | None = None,
        radius: float | None = None,
        inner_radius: float = 0,
        start_angle: float = -90,
        x_range: str | None = None,
        y_range: str | None = None,
        rows: int | None = None,
        cols: int | None = None,
        padding: float = 20,
        gap: float = 20,
        area: str | None = None,
    ) -> str:
        """为图表类型计算精确的 SVG 像素坐标。

        支持的 chart_type：bar（柱状图）、pie（饼图）、donut（环形图）、
        line（折线图）、radar（雷达图）、grid（网格布局）。

        data 格式："标签1:数值1,标签2:数值2,..."
        如 "华东:185,华南:142,华北:98,西南:76"
        line 模式用 "x1:y1,x2:y2,..."

        生成柱状图/饼图/折线等数据图表前，先用此工具获取元素精确位置再写入 SVG。
        """
        from app.services.ppt.svg_position_calculator import calculate_positions

        try:
            result = calculate_positions(
                chart_type=chart_type,
                data=data,
                format=format,
                bar_width=bar_width,
                gap_ratio=gap_ratio,
                horizontal=horizontal,
                center=center,
                radius=radius,
                inner_radius=inner_radius,
                start_angle=start_angle,
                x_range=x_range,
                y_range=y_range,
                rows=rows,
                cols=cols,
                padding=padding,
                gap=gap,
                area=area,
            )
            return result
        except ValueError as e:
            return f"参数错误：{e}"
        except Exception as e:
            return f"计算失败：{e}"
