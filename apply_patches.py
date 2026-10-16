# -*- coding: utf-8 -*-
"""对 pip 安装的 pdf2zh 1.7.9 自动应用本项目修复补丁（幂等，可重复运行）。

用法:  python apply_patches.py
"""
import io
import os
import sys

_REPLACEMENTS = [
    (
        "high_level.py",
        [
            (
                "        image = np.fromstring(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)[:, :, ::-1]",
                "        image = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)[:, :, ::-1]",
            ),
        ],
    ),
    (
        "converter.py",
        [
            (
                "from tenacity import retry, wait_fixed\n",
                "from tenacity import retry, wait_fixed, stop_after_attempt\n"
                "\n"
                "_translate_fallbacks = 0  # 段落翻译最终失败（如限流）而保留原文的次数\n",
            ),
            (
                "                            pstk.append([child.y0,child.x0,child.x0,child.x0,child.size,child.font,False])",
                "                            pstk.append([child.y0,child.x0,child.x0,child.x0,child.size,child.font,False,True])",
            ),
            (
                "                    cls=layout[cy,cx]\n"
                "                    # if log.isEnabledFor(logging.DEBUG):",
                "                    cls=layout[cy,cx]\n"
                "                    if pstk and pstk[-1][7] and cls==xt_cls and child.size<pstk[-1][4]*0.79 and pstk[-1][4]>12: # 首字下沉校正：以第二个字符重建段落基准字号\n"
                "                        pstk[-1][0]=child.y0\n"
                "                        pstk[-1][4]=child.size\n"
                "                        pstk[-1][5]=child.font\n"
                "                        pstk[-1][7]=False\n"
                "                    # if log.isEnabledFor(logging.DEBUG):",
            ),
            (
                "            @retry(wait=wait_fixed(1))",
                "            @retry(wait=wait_fixed(1), stop=stop_after_attempt(2))",
            ),
            (
                "                    if new is None:\n"
                "                        new=self.translator.translate(s)\n"
                "                        new=remove_control_characters(new)\n"
                "                        cache.write_paragraph(hash_key, hash_key_paragraph, new)",
                "                    if new is None:\n"
                "                        new=self.translator.translate(s)\n"
                "                        new=remove_control_characters(new)\n"
                "                        if not new or not new.strip() or (new.strip()==s.strip() and re.search(r'[A-Za-z]{2}', s)):\n"
                "                            raise RuntimeError(\"Empty or untranslated result\")\n"
                "                        cache.write_paragraph(hash_key, hash_key_paragraph, new)",
            ),
            (
                "            with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread) as executor:\n"
                "                news = list(executor.map(worker, sstk))",
                "            def worker_safe(s): # 最终失败时保留原文，避免整篇卡死\n"
                "                try:\n"
                "                    return worker(s)\n"
                "                except BaseException:\n"
                "                    global _translate_fallbacks\n"
                "                    _translate_fallbacks += 1\n"
                "                    return s\n"
                "            with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread) as executor:\n"
                "                news = list(executor.map(worker_safe, sstk))",
            ),
        ],
    ),
    (
        "translator.py",
        [
            (
                "        response = self.session.get(\n"
                "            self.base_link,\n"
                "            params={\"tl\": self.lang_out, \"sl\": self.lang_in, \"q\": text},\n"
                "            headers=self.headers,\n"
                "        )",
                "        response = self.session.get(\n"
                "            self.base_link,\n"
                "            params={\"tl\": self.lang_out, \"sl\": self.lang_in, \"q\": text},\n"
                "            headers=self.headers,\n"
                "            timeout=15,\n"
                "        )",
            ),
        ],
    ),
]


def find_pdf2zh_dir():
    try:
        import pdf2zh
    except ImportError:
        print("未找到 pdf2zh，请先执行: pip install pdf2zh==1.7.9")
        sys.exit(1)
    return os.path.dirname(os.path.abspath(pdf2zh.__file__))


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else find_pdf2zh_dir()
    print("pdf2zh 目录:", base)
    all_ok = True
    for fname, pairs in _REPLACEMENTS:
        path = os.path.join(base, fname)
        if not os.path.exists(path):
            print("[缺少文件]", fname)
            all_ok = False
            continue
        src = io.open(path, encoding="utf-8").read()
        for old, new in pairs:
            if old in src:
                src = src.replace(old, new, 1)
                print("[已修补]", fname, "|", new.splitlines()[0].strip()[:52])
            elif new in src:
                print("[已是修补版]", fname, "|", new.splitlines()[0].strip()[:52])
            else:
                print("[匹配失败]", fname, "|", old.splitlines()[0].strip()[:52])
                all_ok = False
        io.open(path, "w", encoding="utf-8", newline="").write(src)
    print("全部完成 ✔" if all_ok else "存在未匹配的修改，请检查 pdf2zh 版本是否为 1.7.9")


if __name__ == "__main__":
    main()
