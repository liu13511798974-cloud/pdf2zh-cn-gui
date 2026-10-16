$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath('Desktop')
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'PDF文献翻译工具.lnk'))
$sh.TargetPath = Join-Path $dir '启动翻译工具.bat'
$sh.WorkingDirectory = $dir
$sh.Save()
