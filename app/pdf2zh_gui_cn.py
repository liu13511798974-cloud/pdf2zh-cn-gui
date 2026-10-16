# -*- coding: utf-8 -*-
"""PDF 文献翻译工具（中文界面，带实时进度）
运行：python pdf2zh_gui_cn.py   然后浏览器打开 http://127.0.0.1:7860
"""

import os
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path

import gradio as gr
import numpy as np
import pymupdf

_HERE = Path(__file__).resolve().parent
if os.environ.get("PDF2ZH_OUT_DIR"):
    OUT_DIR = Path(os.environ["PDF2ZH_OUT_DIR"])
elif _HERE.name == "app" and (_HERE.parent / "python").exists():
    # 便携包布局：<包目录>\app\pdf2zh_gui_cn.py -> 输出到 <包目录>\翻译输出
    OUT_DIR = _HERE.parent / "翻译输出"
else:
    OUT_DIR = _HERE / "翻译输出"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SERVICES = {
    "Google 翻译（免费，推荐）": "google",
    "DeepL（官网可注册免费密钥）": "deepl",
    "DeepLX（免费自建服务）": "deeplx",
    "Ollama（本地大模型，需填模型名）": "ollama",
    "OpenAI 兼容 / DeepSeek（需密钥，质量最佳）": "openai",
    "Azure 翻译（需 AZURE_APIKEY 密钥）": "azure",
}
LANGS = {
    "中文": "zh",
    "English": "en",
    "日本語": "ja",
    "한국어": "ko",
    "Français": "fr",
    "Deutsch": "de",
    "Русский": "ru",
    "Español": "es",
    "Italiano": "it",
}

STATE = {
    "stage": "idle",
    "pages_done": 0,
    "pages_total": None,
    "paras_done": 0,
    "paras_fail": 0,
}


class DummyProgress:
    def __call__(self, value=None, desc=None, total=None):
        return None


def parse_pages(s):
    s = (s or "").strip()
    if not s:
        return None
    pages = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            pages.extend(range(int(a) - 1, int(b)))
        else:
            pages.append(int(part) - 1)
    return pages


def _install_hooks():
    """统计版面解析页数与段落翻译数，供界面实时显示。"""
    try:
        import tqdm as _tqdm
        from pdf2zh import translator as tr

        class _TQDM(_tqdm.tqdm):
            def __init__(self, iterable=None, total=None, *a, **k):
                super().__init__(iterable, total=total, *a, **k)
                if self.total:
                    STATE["pages_total"] = int(self.total)
                    STATE["pages_done"] = 0

            def __iter__(self):
                for x in super().__iter__():
                    STATE["pages_done"] = int(self.n)
                    yield x

            def update(self, n=1):
                super().update(n)
                STATE["pages_done"] = int(self.n)

        _tqdm.tqdm = _TQDM

        for cls in (
            tr.GoogleTranslator,
            tr.DeepLTranslator,
            tr.DeepLXTranslator,
            tr.OllamaTranslator,
            tr.OpenAITranslator,
            tr.AzureTranslator,
        ):
            if not hasattr(cls, "translate") or getattr(cls.translate, "_cn_patched", False):
                continue
            orig = cls.translate

            def make(orig):
                def wrapper(self, text):
                    try:
                        STATE["paras_done"] += 1
                    except Exception:
                        pass
                    return orig(self, text)

                wrapper._cn_patched = True
                return wrapper

            cls.translate = make(orig)
    except Exception:
        pass


def _probe_service(service):
    """翻译前探活：服务不可用时直接报出具体原因，避免长时间卡住。"""
    base = service.split(":", 1)[0]
    try:
        if base == "google":
            from pdf2zh.translator import GoogleTranslator

            t = GoogleTranslator("google", "zh", "en", None)
            r = t.translate("hello")
            if not r or not r.strip():
                raise RuntimeError("empty response")
        elif base == "openai":
            import openai

            model = service.split(":", 1)[1] if ":" in service else "deepseek-chat"
            client = openai.OpenAI(timeout=15)
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
        elif base == "ollama":
            import requests

            r = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            if r.status_code != 200:
                raise RuntimeError("Ollama 未运行或不可访问 (HTTP %d)" % r.status_code)
        elif base == "deepl":
            if not os.environ.get("DEEPL_AUTH_KEY"):
                raise RuntimeError("未设置 DeepL 密钥")
        elif base == "deeplx":
            if not os.environ.get("DEEPLX_AUTH_KEY"):
                raise RuntimeError("未设置 DeepLX 密钥")
        elif base == "azure":
            for k in ("AZURE_APIKEY", "AZURE_ENDPOINT", "AZURE_REGION"):
                if not os.environ.get(k):
                    raise RuntimeError("未设置 %s" % k)
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def _status_text():
    pages = STATE.get("pages_total")
    page_info = (
        f"版面解析 {STATE['pages_done']}/{pages} 页"
        if pages
        else f"版面解析 {STATE['pages_done']} 页"
    )
    para_info = f"段落翻译完成 {STATE['paras_done']} 段"
    fail = STATE.get("paras_fail", 0)
    if fail:
        para_info += f"，失败 {fail} 段（失败段落会保留原文）"
    return f"⏳ 正在翻译…{page_info}；{para_info}。页数越多耗时越长，请耐心等待。"


def _translate_core(file_obj, service, lang_label, pages_str):
    src = file_obj.name if hasattr(file_obj, "name") else str(file_obj)
    stem = Path(src).stem
    lang_out = LANGS.get(lang_label, "zh")
    pages = parse_pages(pages_str)

    work = OUT_DIR / f"w_{uuid.uuid4().hex[:10]}"
    work.mkdir(parents=True, exist_ok=True)
    tmp_in = work / "input.pdf"
    try:
        shutil.copyfile(src, tmp_in)
    except Exception as e:
        return None, None, None, f"❌ 读取文件失败：{e}"

    old_cwd = os.getcwd()
    fallbacks = 0
    try:
        os.chdir(work)
        from pdf2zh import converter as conv
        from pdf2zh.pdf2zh import extract_text

        conv._translate_fallbacks = 0
        extract_text(
            files=[str(tmp_in)],
            pages=pages,
            service=service,
            lang_in="auto",
            lang_out=lang_out,
            thread=8,
        )
        fallbacks = getattr(conv, "_translate_fallbacks", 0)
    except Exception as e:
        tb = traceback.format_exc()
        return None, None, None, f"❌ 翻译失败：{e}\n\n{tb[-900:]}"
    finally:
        os.chdir(old_cwd)

    zh_src = work / "input-zh.pdf"
    dual_src = work / "input-dual.pdf"
    if not zh_src.exists():
        return None, None, None, "❌ 未生成输出文件，请检查控制台日志"

    safe_stem = stem[:120].rstrip(" .")
    zh_dst = OUT_DIR / f"{safe_stem}-中文版.pdf"
    dual_dst = OUT_DIR / f"{safe_stem}-中英对照版.pdf"
    shutil.copyfile(zh_src, zh_dst)
    dual_ok = dual_src.exists()
    if dual_ok:
        shutil.copyfile(dual_src, dual_dst)

    preview = None
    try:
        doc = pymupdf.open(str(zh_dst))
        pix = doc[0].get_pixmap()
        preview = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
        doc.close()
    except Exception:
        pass

    shutil.rmtree(work, ignore_errors=True)

    msg = f"✅ 翻译完成！文件已保存到：{OUT_DIR}\\{zh_dst.name}"
    if dual_ok:
        msg += f"\n中英对照版：{OUT_DIR}\\{dual_dst.name}"
    if fallbacks:
        msg += f"\n⚠️ 有 {fallbacks} 段因翻译服务限流/失败而保留原文，稍后重新翻译即可补全。"
    return str(zh_dst), (str(dual_dst) if dual_ok else None), preview, msg


def do_translate(
    file_obj, service_label, lang_label, pages_str, model_id, api_key, base_url, deepl_key,
    progress=gr.Progress(track_tqdm=True),
):
    if progress is None:
        progress = DummyProgress()

    if not file_obj:
        yield None, None, None, "⚠️ 请先上传 PDF 文件再点开始翻译"
        return

    # 1) 先组装引擎与密钥环境（必须在探活之前设置，否则探活会误报未配置）
    service = SERVICES.get(service_label, "google")
    model_id = (model_id or "").strip()
    if service in ("ollama", "openai"):
        if service == "openai" and not model_id:
            model_id = "deepseek-chat"
        if model_id:
            service = f"{service}:{model_id}"
    if (api_key or "").strip():
        os.environ["OPENAI_API_KEY"] = api_key.strip()
    if (base_url or "").strip():
        os.environ["OPENAI_BASE_URL"] = base_url.strip()
    if (deepl_key or "").strip():
        os.environ["DEEPL_AUTH_KEY"] = deepl_key.strip()
        os.environ["DEEPL_SERVER_URL"] = "https://api-free.deepl.com"

    # 重置状态
    STATE.update(stage="probe", pages_done=0, pages_total=None, paras_done=0, paras_fail=0)
    _install_hooks()

    progress(0.01, desc="正在检查翻译服务…")
    err = _probe_service(service)
    if err:
        yield None, None, None, (
            "❌ 翻译服务连接失败，已停止任务（不会长时间卡住）。\n\n"
            f"引擎：{service_label}\n原因：{err}\n\n"
            "排查建议：\n"
            "· DeepSeek：确认密钥已填且有效（sk- 开头），接口地址为 https://api.deepseek.com，模型名 deepseek-chat；\n"
            "· OpenAI：接口地址需填 https://api.openai.com/v1；\n"
            "· Google：可能被临时限流，等 5~10 分钟再试；\n"
            "· DeepL：免费密钥需在 deepl.com 注册。"
        )
        return

    result = {}

    def runner():
        try:
            result["v"] = _translate_core(file_obj, service, lang_label, pages_str)
        except Exception as e:
            result["v"] = (None, None, None, f"❌ 发生异常：{e}\n{traceback.format_exc()[-600:]}")

    STATE["stage"] = "working"
    t = threading.Thread(target=runner, daemon=True)
    t.start()

    while t.is_alive():
        try:
            STATE["paras_fail"] = __import__("pdf2zh").converter._translate_fallbacks
        except Exception:
            pass
        yield None, None, None, _status_text()
        time.sleep(1.0)

    yield result.get("v", (None, None, None, "❌ 任务异常结束"))


def set_busy():
    return "⏳ 正在启动任务…（如翻译服务被限流，会立即提示，不会一直卡住）"


with gr.Blocks(title="PDF 文献翻译工具（中文界面）") as demo:
    gr.Markdown(
        "# 📄 PDF 文献翻译工具\n"
        "**英文文献 → 中文**：保留原排版，公式与图片不翻译；输出「中文版」与「中英对照版」两份 PDF。"
    )

    with gr.Row():
        with gr.Column(scale=1):
            file_input = gr.File(
                label="① 上传 PDF 文件",
                file_count="single",
                file_types=[".pdf"],
                type="filepath",
            )
            service = gr.Dropdown(
                label="② 翻译引擎",
                choices=list(SERVICES.keys()),
                value="Google 翻译（免费，推荐）",
            )
            lang_to = gr.Dropdown(
                label="③ 目标语言",
                choices=list(LANGS.keys()),
                value="中文",
            )
            with gr.Accordion("🔑 模型与密钥设置（可选，仅在选择相应引擎时需要）", open=False):
                model_id = gr.Textbox(
                    label="模型名称（Ollama / OpenAI 兼容引擎用）",
                    placeholder="OpenAI 兼容默认 deepseek-chat；Ollama 如 gemma2",
                    value="",
                )
                api_key = gr.Textbox(
                    label="OpenAI 兼容密钥（DeepSeek / OpenAI）",
                    placeholder="sk-…（DeepSeek 密钥在 platform.deepseek.com 申请，价格极低）",
                    value="",
                    type="password",
                )
                base_url = gr.Textbox(
                    label="OpenAI 兼容接口地址",
                    value="https://api.deepseek.com",
                    info="DeepSeek 保持默认；OpenAI 官方填 https://api.openai.com/v1",
                )
                deepl_key = gr.Textbox(
                    label="DeepL 密钥（免费版）",
                    placeholder="在 deepl.com 注册免费 API 后填入",
                    value="",
                    type="password",
                )
            pages_str = gr.Textbox(
                label="④ 页码范围（可选）",
                info="留空 = 翻译全文；支持 1-3、2,5,8-10 这种写法",
                value="",
            )
            translate_btn = gr.Button("开始翻译", variant="primary")
            status = gr.Markdown("💡 上传 PDF 后点击「开始翻译」即可。翻译过程中此处会实时显示进度。")
            gr.Markdown("### 📥 下载结果")
            file_zh = gr.File(label="中文版 PDF")
            file_dual = gr.File(label="中英对照版 PDF")
        with gr.Column(scale=2):
            preview = gr.Image(label="译文第 1 页预览")

    translate_btn.click(set_busy, outputs=status).then(
        do_translate,
        inputs=[file_input, service, lang_to, pages_str, model_id, api_key, base_url, deepl_key],
        outputs=[file_zh, file_dual, preview, status],
    )

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1)
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PDF2ZH_PORT", "7860")),
        inbrowser=os.environ.get("PDF2ZH_INBROWSER", "1") == "1",
        show_error=True,
        ssr_mode=False,
        share=False,
    )
