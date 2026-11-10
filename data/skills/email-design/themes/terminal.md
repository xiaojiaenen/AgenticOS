# Theme · terminal（暗底工程现场 / 等宽克制）

## 气质
暗底、等宽、仪表信号般的克制。像监控大屏上一条通知：给工程同学看的、讲系统或事故的
邮件。信息密度高一点没关系，但要**扫得清**。不是"科技感炫技"，是"现场记录"。

## 适合 / 不适合
- **适合**：技术事故复盘、系统变更通知、发布公告、给工程/运维群体的邮件。
- **不适合**：面向非技术客户；需要打印的正式文档（暗底费墨）；需要温度的沟通。

## 调色（深色系）
| token | 值 | 用途 |
|---|---|---|
| bg | `#0a1512` | 页面底 + 卡片底（墨绿黑，不是纯黑） |
| panel | `#0e1c18` | 略亮一层的容器 |
| line | `#1c302a` | 分割线/描边 |
| text | `#e8f1ec` | 主文字（米白偏绿） |
| sub | `#9db5aa` | 次要文字 |
| signal | `#cf9a34` | 琥珀信号色：记号/按钮（只此一处亮色） |
| ok | `#4f9d72` | 状态：成功 |
| warn | `#c15a54` | 状态：失败/告警 |

## 排版
- 标题可无衬线粗排或等宽，`22–30px / 700`。
- 数据/编号/时间戳用等宽：`'SFMono-Regular', Menlo, Consolas, 'Courier New', monospace`。
- 正文 `14–15px / 400 / lh 1.8`，米白。

## 版式
暗底卡片；页眉左品牌 + 右状态（小圆点+文字）；一块内容牌用左侧 3px 琥珀立边；
键值表用等宽右值。记忆点是**暗底 + 一枚琥珀信号**。

```
█ 琥珀顶线
AgenticOS                    ● 已恢复
────────────────────────────
系统事故复盘（标题）

▎ 内容牌（左侧琥珀立边）
│ 摘要……

耗时        2 分 18 秒  (等宽)
影响范围    华东区

[回到控制台]
```

## 完整 HTML

```html
<div style="margin:0;padding:0;background:#0a1512;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0a1512;">
<tr><td align="center" style="padding:48px 16px;">
  <table width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;background:#0e1c18;border:1px solid #1c302a;">
    <tr><td style="height:3px;background:#cf9a34;font-size:0;line-height:0;">&nbsp;</td></tr>
    <!-- 页眉 -->
    <tr><td style="padding:24px 34px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:14px;font-weight:700;color:#e8f1ec;">AgenticOS</td>
        <td align="right">
          <table cellpadding="0" cellspacing="0" border="0" align="right"><tr>
            <td style="width:7px;"><div style="width:7px;height:7px;background:#4f9d72;border-radius:7px;font-size:0;line-height:0;">&nbsp;</div></td>
            <td style="padding-left:7px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;font-size:12px;color:#9db5aa;">已恢复</td>
          </tr></table>
        </td>
      </tr></table>
    </td></tr>
    <!-- 标题 -->
    <tr><td style="padding:30px 34px 0;">
      <div style="font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:26px;font-weight:800;line-height:1.25;color:#e8f1ec;letter-spacing:-0.01em;">支付回调 13 分钟中断复盘</div>
    </td></tr>
    <!-- 内容牌 -->
    <tr><td style="padding:22px 34px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0a1512;border-left:3px solid #cf9a34;">
        <tr><td style="padding:20px 22px;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC','Microsoft YaHei',sans-serif;font-size:14px;line-height:1.8;color:#c2d3ca;">14:02 起因是上游对账服务主备切换超时，回调堆积。14:15 切到备用通道后恢复，期间约 1.2 万笔回调延迟，无资金损失。</td></tr>
      </table>
    </td></tr>
    <!-- 键值表 -->
    <tr><td style="padding:20px 34px 0;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="padding:11px 0;border-bottom:1px solid #1c302a;font-family:'PingFang SC','Microsoft YaHei',sans-serif;font-size:13px;color:#9db5aa;">影响时长</td>
          <td align="right" style="padding:11px 0;border-bottom:1px solid #1c302a;font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:13px;color:#e8f1ec;">13m 07s</td>
        </tr>
        <tr>
          <td style="padding:11px 0;font-family:'PingFang SC','Microsoft YaHei',sans-serif;font-size:13px;color:#9db5aa;">延迟回调</td>
          <td align="right" style="padding:11px 0;font-family:'SFMono-Regular',Menlo,Consolas,monospace;font-size:13px;color:#e8f1ec;">≈12,000</td>
        </tr>
      </table>
    </td></tr>
    <tr><td style="padding:24px 34px 0;">
      <table cellpadding="0" cellspacing="0" border="0"><tr>
        <td style="background:#cf9a34;border-radius:6px;">
          <a href="https://example.com/console" style="display:inline-block;padding:11px 26px;color:#1a1206;font-size:14px;font-weight:700;text-decoration:none;font-family:'Helvetica Neue',Helvetica,Arial,'PingFang SC',sans-serif;">回到控制台</a>
        </td>
      </tr></table>
    </td></tr>
    <tr><td style="padding:24px 34px 0;"><div style="height:1px;background:#1c302a;font-size:0;line-height:0;">&nbsp;</div></td></tr>
    <tr><td style="padding:14px 34px 26px;font-family:'PingFang SC','Microsoft YaHei',sans-serif;font-size:12px;color:#7f9c90;">AgenticOS · 值班通道</td></tr>
  </table>
</td></tr>
</table>
</div>
```

## 禁止项
- 用纯黑 #000（用带绿相的深墨 #0a1512，有"纸"的温度）
- 多个亮色信号（只有琥珀一个）
- 深底上放低对比的浅灰小字（读不清）
- 把深底理解成"炫酷科技风"——它是克制的现场记录
