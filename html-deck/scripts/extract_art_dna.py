#!/usr/bin/env python3
"""从项目图片提取可复现的艺术表达 DNA，并生成非模板化封面/尾页 SVG 背景。"""
import argparse, colorsys, hashlib, json, math
from pathlib import Path
from common import read_json, write_json

def args():
    p=argparse.ArgumentParser(description="Extract project art DNA and generate cover/closing SVG backgrounds.")
    p.add_argument("--manifest", required=True); p.add_argument("--output", required=True)
    p.add_argument("--assets-dir", required=True); return p.parse_args()

def hexrgb(c): return "#%02x%02x%02x" % c

def analyze(path):
    from PIL import Image, ImageFilter
    im=Image.open(path).convert("RGB"); im.thumbnail((180,180)); px=list(im.getdata())
    q=im.quantize(colors=6, method=2).convert("RGB"); palette=[]
    for _,c in sorted(q.getcolors(q.width*q.height), reverse=True)[:5]:
        if c not in palette: palette.append(c)
    g=im.convert("L"); edge=g.filter(ImageFilter.FIND_EDGES)
    cols=[sum(edge.getpixel((x,y)) for y in range(edge.height)) for x in range(edge.width)]
    rows=[sum(edge.getpixel((x,y)) for x in range(edge.width)) for y in range(edge.height)]
    vertical=sum(cols)/max(1,len(cols)); horizontal=sum(rows)/max(1,len(rows))
    thirds=[]
    for yy in range(3):
        for xx in range(3):
            crop=g.crop((xx*g.width//3,yy*g.height//3,(xx+1)*g.width//3,(yy+1)*g.height//3))
            thirds.append(sum(crop.getdata())/max(1,len(list(crop.getdata()))))
    darkest=min(range(9), key=lambda i:thirds[i]); brightest=max(range(9), key=lambda i:thirds[i])
    sat=sum(colorsys.rgb_to_hsv(r/255,g/255,b/255)[1] for r,g,b in px)/max(1,len(px))
    contrast=(max(thirds)-min(thirds))/255
    return {"palette":[hexrgb(c) for c in palette],"line_language":"纵向生长" if vertical>horizontal*1.08 else "横向延展" if horizontal>vertical*1.08 else "均衡网格","dark_focus":[darkest%3,darkest//3],"light_focus":[brightest%3,brightest//3],"saturation":round(sat,3),"contrast":round(contrast,3)}

def svg(dna, kind, seed):
    p=dna["palette"] or ["#111827","#38bdf8","#f8fafc"]
    rnd=lambda n: int(hashlib.sha256(f"{seed}:{kind}:{n}".encode()).hexdigest()[:8],16)
    lines=[]
    vertical=dna["line_language"]=="纵向生长"
    for i in range(18):
        a=rnd(i); x=a%1920; y=(a//1920)%1080; length=180+a%520
        x2=x+(20+a%160 if vertical else length); y2=y+(length if vertical else 20+a%160)
        lines.append(f'<path d="M{x} {y} L{x2} {y2}" stroke="{p[i%len(p)]}" opacity="{.06+(a%16)/100:.2f}" stroke-width="{1+a%4}"/>')
    fx,fy=dna["light_focus"]; cx=(fx+.5)*640; cy=(fy+.5)*360
    shapes=[]
    for i in range(7):
        a=rnd(50+i); r=70+a%260; shapes.append(f'<circle cx="{cx+(a%241)-120}" cy="{cy+((a//241)%181)-90}" r="{r}" fill="none" stroke="{p[(i+1)%len(p)]}" opacity="{.05+i*.018:.3f}" stroke-width="{1+i%3}"/>')
    flip='translate(1920 0) scale(-1 1)' if kind=='closing' else ''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080"><defs><radialGradient id="g"><stop stop-color="{p[1%len(p)]}" stop-opacity=".42"/><stop offset="1" stop-color="{p[0]}" stop-opacity="0"/></radialGradient><linearGradient id="b" x2="1" y2="1"><stop stop-color="{p[0]}"/><stop offset="1" stop-color="{p[-1]}"/></linearGradient></defs><rect width="1920" height="1080" fill="url(#b)"/><g transform="{flip}"><ellipse cx="{cx}" cy="{cy}" rx="680" ry="520" fill="url(#g)"/>{''.join(lines)}{''.join(shapes)}</g></svg>'''

def main():
    a=args(); mp=Path(a.manifest); m=read_json(mp); rows=[]
    for item in m.get("images",[]):
        f=item.get("file"); path=mp.parent/f if f else None
        if path and path.exists(): rows.append((item,analyze(path)))
    if not rows: raise SystemExit("no readable project images")
    primary=max(rows,key=lambda x:{"high":3,"medium":2,"low":1}.get(x[0].get("weight"),1)); dna=primary[1]
    expression=(f"主题色为{'、'.join(dna['palette'][:4])}；线条呈{dna['line_language']}；"
      f"亮部重心位于九宫格({dna['light_focus'][0]+1},{dna['light_focus'][1]+1})，暗部重心位于({dna['dark_focus'][0]+1},{dna['dark_focus'][1]+1})；"
      f"饱和度{dna['saturation']:.2f}、明暗层次{dna['contrast']:.2f}。背景保留标题侧留白，以异尺度轮廓、项目色光晕和方向性线群形成版式节奏；封面展开、尾页镜像收束，禁止复用固定行业图形。")
    outdir=Path(a.assets_dir); outdir.mkdir(parents=True,exist_ok=True); seed=primary[0]["id"]+expression
    cover=outdir/"project-cover.svg"; closing=outdir/"project-closing.svg"
    cover.write_text(svg(dna,"cover",seed),encoding="utf-8"); closing.write_text(svg(dna,"closing",seed),encoding="utf-8")
    report={"version":"1.0","source_image_ids":[x[0]["id"] for x in rows],"primary_image_id":primary[0]["id"],"art_expression":expression,"dna":dna,"cover_background":f"{outdir.name}/{cover.name}","closing_background":f"{outdir.name}/{closing.name}","non_template_signature":hashlib.sha256(seed.encode()).hexdigest()[:16]}
    write_json(a.output,report); print(a.output)
if __name__=="__main__": main()
