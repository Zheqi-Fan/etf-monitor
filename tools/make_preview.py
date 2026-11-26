#!/usr/bin/env python3
"""生成社交分享预览图 assets/preview.png（1200x630，Open Graph 标准尺寸）。

配色与 assets/style.css 的 CITIC CLSA 色系保持一致；改动页面标题或主色后重跑本脚本：
    python3 tools/make_preview.py
仅依赖 Pillow + numpy，不需要浏览器。
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "preview.png")

NAVY = (0, 0, 102)
YELLOW = (255, 241, 0)
RED = (0xC4, 0x26, 0x2C)
WHITE = (255, 255, 255)

F_BOLD = ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2)   # W6
F_REG = ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0)    # W3
F_MONO = ("/System/Library/Fonts/Menlo.ttc", 1)              # Bold


def font(spec, size):
    path, index = spec
    return ImageFont.truetype(path, size, index=index)


def background():
    """对角深蓝渐变 + 右上黄光 + 左下蓝光 + 淡网格。"""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    t = ((x / W) * 0.62 + (y / H) * 0.38)[..., None]

    stops = [(0.00, (0x00, 0x00, 0x24)), (0.52, (0x00, 0x00, 0x50)), (1.00, (0x00, 0x00, 0x80))]
    img = np.zeros((H, W, 3), np.float32)
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        m = ((t[..., 0] >= p0) & (t[..., 0] <= p1)).astype(np.float32)
        local = np.clip((t[..., 0] - p0) / (p1 - p0), 0, 1)[..., None]
        seg = np.array(c0, np.float32) * (1 - local) + np.array(c1, np.float32) * local
        img = np.where(m[..., None] > 0, seg, img)

    def glow(cx, cy, rx, ry, color, alpha):
        d = np.sqrt(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2)
        k = np.clip(1 - d, 0, 1) ** 2.2 * alpha
        return np.array(color, np.float32) * k[..., None]

    img += glow(W * 0.92, 0.02 * H, W * 0.58, H * 0.58, YELLOW, 0.22)
    img += glow(W * 0.08, H * 1.18, W * 0.63, H * 0.66, (0x02, 0x02, 0xB5), 0.42)
    return np.clip(img, 0, 255)


def grid(layer, step=52, alpha=0.035):
    """白网格，向下淡出（对应页面 hero 的 mask）。"""
    g = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(g)
    for gx in range(0, W, step):
        d.line([(gx, 0), (gx, H)], fill=255)
    for gy in range(0, H, step):
        d.line([(0, gy), (W, gy)], fill=255)
    fade = np.clip(1 - np.mgrid[0:H, 0:W][0] / H / 0.92, 0, 1) ** 1.2
    a = (np.array(g, np.float32) / 255) * fade * alpha * 255
    layer.paste(Image.new("RGB", (W, H), WHITE), (0, 0), Image.fromarray(a.astype(np.uint8)))


def draw_text(d, xy, text, f, fill, spacing=0):
    if not spacing:
        d.text(xy, text, font=f, fill=fill)
        return
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + spacing


def main():
    base = Image.fromarray(background().astype(np.uint8), "RGB")
    grid(base, alpha=0.04)
    d = ImageDraw.Draw(base)
    d.rectangle([0, 0, W, 6], fill=RED)

    # 品牌行
    mark = (84, 72, 84 + 44, 72 + 44)
    d.rounded_rectangle(mark, radius=11, fill=RED, outline=RED, width=1)
    f_sf = font(F_MONO, 16)
    bw = d.textlength("SF", font=f_sf)
    d.text((mark[0] + (44 - bw) / 2, mark[1] + 13), "SF", font=f_sf, fill=WHITE)

    draw_text(d, (144, 76), "STATE FLOW", font(F_BOLD, 13, ), WHITE, spacing=3.2)
    d.text((144, 96), "宽基 ETF 资金流研究台", font=font(F_REG, 12), fill=(150, 155, 190))

    # 主标题
    f_h1 = font(F_BOLD, 74)
    d.text((84, 214), "宽基", font=f_h1, fill=WHITE)
    d.text((84 + d.textlength("宽基", font=f_h1) + 16, 214), "ETF", font=f_h1, fill=WHITE)
    d.text((84, 302), "资金流监测", font=f_h1, fill=YELLOW)

    # 导语
    lede = (185, 190, 214)
    d.text((84, 452), "中央汇金 / 证金 / 国新 / 诚通等机构 · 借道宽基 ETF 的一级市场净申购",
           font=font(F_REG, 18), fill=lede)
    d.text((84, 484), "Δ份额 × 净值日频估算 · 核心 10 只覆盖 96% 规模 · 2018-01 至今",
           font=font(F_REG, 18), fill=lede)

    # 页脚
    d.line([(84, 552), (W - 84, 552)], fill=(64, 68, 120), width=1)
    d.rectangle([84, 574, 90, 580], fill=RED)
    d.text((100, 568), "State Flow · 研究工具，不构成投资建议",
           font=font(F_REG, 13), fill=(132, 137, 172))
    url = "zheqi-fan.github.io/etf-monitor"
    f_url = font(F_MONO, 13)
    d.text((W - 84 - d.textlength(url, font=f_url), 569), url, font=f_url, fill=(132, 137, 172))

    base.save(OUT, optimize=True)
    print(f"saved {OUT}  {base.size[0]}x{base.size[1]}  {os.path.getsize(OUT) // 1024} KB")


if __name__ == "__main__":
    main()
