# 实战案例：iHand55 数据手册 英 → 西

原稿：Hi-Target iHand55 现场控制器（2 页 A4，Illustrator 导出）
产出：`iHand55-Professional-Field-Controller-ES.pdf`

## 文档结构

| 页 | 内容 | 关键技术点 |
|---|---|---|
| 1 | 封面：整幅雪山照片 + 橙色弧线 + 白色标题 | 文字直接压在位图上，挖字后必须保留底图 |
| 2 | 卖点（图 + 4 个金色图标）+ 规格表 + 页脚二维码 | 表格由「整列渐变填充块」构成，无单元格线 |

## 踩到的具体问题与结论

1. **封面挖字会留白块吗？**
   不会。`fill=None` + `images=PDF_REDACT_IMAGE_NONE` 时只删文字对象，底图不动。
   挖完直接写白字，渐变过渡自然，看不出补丁。

2. **表格行高只有 11.5–14.7pt，一行就是一行**
   第一版想把 `Input Configuration` 直译成 `Configuración de entrada` 放在 9pt 里，
   宽度 94.3pt 而格内可用 91.9pt，贴边。方案：不换行、不缩太多，
   靠 `maxw` 自动缩到 8.8pt（差 2%，肉眼不可辨）。

3. **两处标签必须缩写**
   `Operating temperature` → `Temp. de funcionamiento`
   `Storage temperature` → `Temp. de almacenaje`
   全称 `Temperatura de almacenamiento` 在 9pt 下约 104pt，列宽只有 98.9pt，塞不进。

4. **标题 `KEY FEATURES` 不能直译**
   右侧 175pt 处就是图标，`maxw` 只有 133pt。
   `CARACTERÍSTICAS CLAVE` 约 185pt 会压到图标，改用 `CARACTERÍSTICAS`。

5. **一个分类标签跨多行合并单元格**
   `Physical Features` 原文一行，译文 `Características físicas` 需要两行。
   该合并单元格高度充足，设 `max_lines: 2` + `valign: "center"`，
   两行落在 617.7 / 629.7，正好在原文本中心上下对称。

6. **卖点段落行数变化**
   原文每条 2–3 行。译文强制控制在原文行数内，
   因为下一条的起始 y 是固定的，多一行就会撞上。

7. **页脚地址必须压缩**
   `DIR.: ... Distrito de Panyu, 511400 Guangzhou, China.` 比英文长约 9%，
   超出 494pt 页宽，脚本自动缩到 7.6pt 贴合右边界。

## 校验结果

```
页数 2/2   尺寸 (595.3, 807.9) / (595.3, 807.9)
原文残留：无
校验通过：无残留、无越界、无重叠
```

产出 0.47 MB，字体子集内嵌（Calibri / Arial / Verdana），任意设备打开不掉字。
