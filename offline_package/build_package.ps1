# -*- coding: utf-8 -*-
# 构建离线便携包（Windows）。用法：
#   powershell -ExecutionPolicy Bypass -File build_package.ps1
# 产物：dist\PDF-Translator-Portable（文件夹）和同名 .zip
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $root
$dist = Join-Path $root "dist\PDF-Translator-Portable"
$wheels = Join-Path $dist "wheels"
$res = Join-Path $dist "resources"
$modelRoot = Join-Path $dist "model_cache\hf_home\hub\models--juliozhao--DocLayout-YOLO-DocStructBench"
$snap = Join-Path $modelRoot "snapshots\8c3299a30b8ff29a1503c4431b035b93220f7b11"
$refs = Join-Path $modelRoot "refs"

function Download($url, $dest) {
    Write-Host "  下载: $url"
    Invoke-WebRequest -Uri $url -OutFile $dest -TimeoutSec 900
}

if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
New-Item -ItemType Directory -Force -Path $wheels, $res, "$dist\app", "$dist\patches", $snap, $refs | Out-Null

Write-Host "[1/5] 下载依赖 wheels（约 500 MB，请耐心等待）..."
pip download pdf2zh==1.7.9 --dest $wheels --only-binary=:all: --platform win_amd64 --python-version 3.13 -c (Join-Path $root "constraints.txt")
pip download pip setuptools wheel --dest $wheels --only-binary=:all: --platform win_amd64 --python-version 3.13

Write-Host "[2/5] 下载运行时（Python 3.13 嵌入式 / VC 运行库 / get-pip）..."
Download "https://www.python.org/ftp/python/3.13.15/python-3.13.15-embed-amd64.zip" (Join-Path $res "python-3.13.15-embed-amd64.zip")
Download "https://aka.ms/vs/17/release/vc_redist.x64.exe" (Join-Path $res "vc_redist.x64.exe")
Download "https://bootstrap.pypa.io/get-pip.py" (Join-Path $res "get-pip.py")

Write-Host "[3/5] 下载版面分析模型（约 80 MB）..."
$modelFile = Join-Path $snap "doclayout_yolo_docstructbench_imgsz1024.pt"
try {
    Download "https://huggingface.co/juliozhao/DocLayout-YOLO-DocStructBench/resolve/main/doclayout_yolo_docstructbench_imgsz1024.pt" $modelFile
} catch {
    Write-Host "  官方源失败，改用国内镜像 hf-mirror.com ..."
    Download "https://hf-mirror.com/juliozhao/DocLayout-YOLO-DocStructBench/resolve/main/doclayout_yolo_docstructbench_imgsz1024.pt" $modelFile
}
[IO.File]::WriteAllText((Join-Path $refs "main"), "8c3299a30b8ff29a1503c4431b035b93220f7b11")

Write-Host "[4/5] 复制代码、补丁与安装脚本..."
Copy-Item "$repo\app\*" "$dist\app\" -Force
Copy-Item "$repo\patches\*" "$dist\patches\" -Force
Copy-Item "$root\安装.bat" $dist -Force
Copy-Item "$root\启动翻译工具.bat" $dist -Force
Copy-Item "$root\make_shortcut.ps1" $dist -Force
Copy-Item "$repo\README.md" "$dist\使用说明.md" -Force

Write-Host "[5/5] 压缩为 ZIP..."
$zip = Join-Path $root "dist\PDF-Translator-Portable.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$dist\*" -DestinationPath $zip -CompressionLevel Optimal

Write-Host ""
Write-Host "完成！"
Write-Host "  文件夹: $dist"
Write-Host "  压缩包: $zip"
Write-Host "把文件夹或压缩包拷到新电脑，双击 安装.bat 即可（全程离线）。"
