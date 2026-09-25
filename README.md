# 小说提取器

一个在 Windows 本地运行的小说章节提取工具。输入小说目录页网址后，程序会识别章节、提取正文，并将内容保存为 UTF-8 TXT 文件。

## 功能

- Tkinter 图形界面，显示运行日志和提取进度
- 自动识别目录页章节链接和正文区域
- 支持章节分页，并按网站域名保存识别规则
- 支持 RapidOCR 识别图片正文（安装完整依赖后启用）
- 校验章节长度，并把整本书导出到 TXT

## 环境要求

- Windows 10 或更新版本
- Python 3.10 或更新版本

## 从源码运行

```powershell
python -m pip install -r requirements.txt
python src/main.py
```

也可以在 Windows 上运行 `build.bat`，脚本会安装依赖并生成 `小说提取器.exe`。默认优先使用 `D:\Anaconda\python.exe`（可以根据个人python安装目录选择），否则会尝试从 `PATH` 查找 Python。

## 使用方法

1. 打开小说目录页，复制网页地址。
2. 在程序中粘贴网址并选择 TXT 输出目录。
3. 点击“开始提取”，在界面查看进度和日志。

提取结果按“书名_作者.txt”命名；如果同名文件已存在，会自动添加编号以避免覆盖。

## 项目结构

```text
src/
  main.py       图形界面与任务流程
  extractor.py  网页抓取、章节识别、分页和 OCR
requirements.txt
build.bat
```

本地配置文件和自动学习的站点规则不会提交到版本库。程序抓取效果取决于网站页面结构、网络状态和站点访问规则。请仅提取你有权访问和保存的内容，并遵守相关网站条款及著作权规定。

## 许可证

本项目采用 MIT License，见 [LICENSE](LICENSE)。
