#!/usr/bin/env python3
"""从项目图片提取可复现的艺术表达 DNA，并生成非模板化封面/尾页 SVG 背景。"""
import argparse, colorsys, hashlib, json, math, struct, zlib
from pathlib import Path
from common import read_json, write_json

def args():
    p=argparse.ArgumentParser(description="Extract project art DNA and generate cover/closing SVG backgrounds.")
    p.add_argument("--manifest", required=True); p.add_argument("--output", required=True)
    p.add_argument("--assets-dir", required=True); return p.parse_args()

def hexrgb(c): return "#%02x%02x%02x" % c

def semantic_palette(px):
    """保留深色基底，同时强制捕获面积较小但有识别度的金属/品牌强调色。"""
    buckets={}
    for c in px:
        key=tuple((v//24)*24+12 for v in c); buckets[key]=buckets.get(key,0)+1
    rows=[]
    for c,count in buckets.items():
        h,s,v=colorsys.rgb_to_hsv(*(x/255 for x in c)); rows.append((c,count,s,v,h))
    dark=min(rows,key=lambda r:(r[0][0]+r[0][1]+r[0][2]))[0]
    dominant=max(rows,key=lambda r:r[1])[0]
    accent=max(rows,key=lambda r:r[1]*(.25+r[2]**1.7)*(.25+r[3]))[0]
    warm=max(rows,key=lambda r:r[1]*r[2]*r[3] if .045<r[4]<.19 and r[3]>.28 else 0)[0]
    light=max(rows,key=lambda r:(sum(r[0]),r[1]))[0]
    cool=max(rows,key=lambda r:r[1]*(.2+r[2]) if .50<r[4]<.72 else 0)[0]
    result=[]
    for c in (dark,warm,cool,light,accent,dominant):
        if c not in result: result.append(c)
    return [hexrgb(c) for c in result]

def analyze(path):
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return analyze_png(path)
    im=Image.open(path).convert("RGB"); im.thumbnail((180,180)); px=list(im.getdata())
    palette=semantic_palette(px)
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
    # TASK-022 fix: semantic_palette 已返回 hex 字符串列表，禁止二次 hexrgb（原双重转换在 Pillow 路径下必抛 TypeError）
    return {"palette":palette,"line_language":"纵向生长" if vertical>horizontal*1.08 else "横向延展" if horizontal>vertical*1.08 else "均衡网格","dark_focus":[darkest%3,darkest//3],"light_focus":[brightest%3,brightest//3],"saturation":round(sat,3),"contrast":round(contrast,3)}

def analyze_png(path):
    """无 Pillow 降级：用标准库解码 8-bit 非交错 RGB/RGBA PNG。"""
    raw=path.read_bytes()
    if raw[:8]!=b'\x89PNG\r\n\x1a\n': raise RuntimeError("Pillow 缺失且输入不是受支持的 PNG")
    pos=8; data=b''; width=height=ctype=None
    while pos<len(raw):
        n=struct.unpack('>I',raw[pos:pos+4])[0]; typ=raw[pos+4:pos+8]; chunk=raw[pos+8:pos+8+n]; pos+=12+n
        if typ==b'IHDR': width,height,depth,ctype,_,_,interlace=struct.unpack('>IIBBBBB',chunk)
        elif typ==b'IDAT': data+=chunk
        elif typ==b'IEND': break
    if depth!=8 or ctype not in (2,6) or interlace: raise RuntimeError("标准库降级仅支持 8-bit 非交错 RGB/RGBA PNG")
    bpp=3 if ctype==2 else 4; stream=zlib.decompress(data); stride=width*bpp; rows=[]; off=0; prev=bytearray(stride)
    def paeth(a,b,c):
        p=a+b-c; pa=abs(p-a); pb=abs(p-b); pc=abs(p-c)
        return a if pa<=pb and pa<=pc else b if pb<=pc else c
    for _ in range(height):
        ft=stream[off]; scan=bytearray(stream[off+1:off+1+stride]); off+=stride+1
        for i in range(stride):
            a=scan[i-bpp] if i>=bpp else 0; b=prev[i]; c=prev[i-bpp] if i>=bpp else 0
            if ft==1: scan[i]=(scan[i]+a)&255
            elif ft==2: scan[i]=(scan[i]+b)&255
            elif ft==3: scan[i]=(scan[i]+((a+b)//2))&255
            elif ft==4: scan[i]=(scan[i]+paeth(a,b,c))&255
        rows.append(scan); prev=scan
    step=max(1,min(width,height)//120); px=[]; lumagrid=[]
    for y in range(0,height,step):
        line=[]
        for x in range(0,width,step):
            i=x*bpp; rgb=tuple(rows[y][i:i+3]); px.append(rgb); line.append(sum(rgb)/3)
        lumagrid.append(line)
    palette=semantic_palette(px)
    thirds=[]; gh=len(lumagrid); gw=len(lumagrid[0])
    for yy in range(3):
        for xx in range(3):
            vals=[lumagrid[y][x] for y in range(yy*gh//3,(yy+1)*gh//3) for x in range(xx*gw//3,(xx+1)*gw//3)]
            thirds.append(sum(vals)/max(1,len(vals)))
    vx=sum(abs(row[x]-row[x-1]) for row in lumagrid for x in range(1,gw)); hy=sum(abs(lumagrid[y][x]-lumagrid[y-1][x]) for y in range(1,gh) for x in range(gw))
    sat=sum(colorsys.rgb_to_hsv(r/255,g/255,b/255)[1] for r,g,b in px)/max(1,len(px)); darkest=min(range(9),key=lambda i:thirds[i]); brightest=max(range(9),key=lambda i:thirds[i])
    return {"palette":palette,"line_language":"纵向生长" if vx>hy*1.08 else "横向延展" if hy>vx*1.08 else "均衡网格","dark_focus":[darkest%3,darkest//3],"light_focus":[brightest%3,brightest//3],"saturation":round(sat,3),"contrast":round((max(thirds)-min(thirds))/255,3)}

def svg(dna, kind, seed):
    """生成同一视觉系统的页面角色变体，而不是只给首尾页换皮。"""
    p=dna["palette"] or ["#071426","#c99848","#f3e4be"]
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
    opacity={"cover":1,"section":.72,"content":.42,"closing":.88}.get(kind,.42)
    # 轨道弧线、星点与火箭上升轴均来自项目图的实际构图语言。
    motif=f'''<g opacity="{opacity}"><path d="M-120 900 Q 650 110 1990 320" fill="none" stroke="{p[2%len(p)]}" stroke-width="2" opacity=".24"/><path d="M60 980 Q 780 280 2050 510" fill="none" stroke="{p[1%len(p)]}" stroke-width="1" stroke-dasharray="8 18" opacity=".42"/><path d="M1450 960 L1450 250" stroke="{p[2%len(p)]}" opacity=".14"/><path d="M1432 300 L1450 250 L1468 300" fill="none" stroke="{p[2%len(p)]}" opacity=".34"/></g>'''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080"><defs><radialGradient id="g"><stop stop-color="{p[1%len(p)]}" stop-opacity=".34"/><stop offset="1" stop-color="{p[0]}" stop-opacity="0"/></radialGradient><linearGradient id="b" x2="1" y2="1"><stop stop-color="{p[0]}"/><stop offset=".62" stop-color="#071426"/><stop offset="1" stop-color="#02070d"/></linearGradient><filter id="grain"><feTurbulence baseFrequency=".8" numOctaves="2" seed="{rnd(99)%99}"/><feColorMatrix values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 .035 0"/></filter></defs><rect width="1920" height="1080" fill="url(#b)"/><g transform="{flip}"><ellipse cx="{cx}" cy="{cy}" rx="680" ry="520" fill="url(#g)"/>{motif}{''.join(lines)}{''.join(shapes)}</g><rect width="1920" height="1080" filter="url(#grain)" opacity=".26"/></svg>'''

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
    cover=outdir/"project-cover.svg"; content=outdir/"project-content.svg"; section=outdir/"project-section.svg"; closing=outdir/"project-closing.svg"
    for path,kind in ((cover,"cover"),(content,"content"),(section,"section"),(closing,"closing")):
        path.write_text(svg(dna,kind,seed),encoding="utf-8")
    report={"version":"2.0","source_image_ids":[x[0]["id"] for x in rows],"primary_image_id":primary[0]["id"],"art_expression":expression,"dna":dna,"cover_background":f"{outdir.name}/{cover.name}","content_background":f"{outdir.name}/{content.name}","section_background":f"{outdir.name}/{section.name}","closing_background":f"{outdir.name}/{closing.name}","non_template_signature":hashlib.sha256(seed.encode()).hexdigest()[:16]}
    write_json(a.output,report); print(a.output)
if __name__=="__main__": main()
