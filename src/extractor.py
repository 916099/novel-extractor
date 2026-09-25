"""
小说提取器核心模块
支持从常见小说网站自动提取章节内容
内置自动适配功能：遇到不支持的网站会自动学习并保存规则
"""
import re
import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin, urlparse
from typing import List, Tuple, Optional, Callable

# OCR相关 - 可选功能（使用RapidOCR，纯Python，无需外部引擎）
try:
    from rapidocr_onnxruntime import RapidOCR
    from PIL import Image
    import io
    OCR_AVAILABLE = True
    _ocr_engine = None
    def get_ocr():
        global _ocr_engine
        if _ocr_engine is None:
            _ocr_engine = RapidOCR()
        return _ocr_engine
except ImportError:
    OCR_AVAILABLE = False
    get_ocr = None


class NovelExtractor:
    """小说提取器 - 支持自动适配新网站"""

    # 常见的章节链接选择器（按优先级排序）
    DEFAULT_CHAPTER_SELECTORS = [
        'div.listmain a',
        '.listmain a',
        '#list a',
        '.box_con a',
        '.directory-list a',
        '.mulu a',
        '#chapter-list a',
        '.chapter-list a',
        'div#chapters a',
        '.volume a',
    ]

    # 常见的正文内容选择器
    DEFAULT_CONTENT_SELECTORS = [
        '#content',
        '.content',
        '#booktxt',
        '.txt_tit',
        '.con',
        '.read-content',
        '.article-content',
        '#htmlContent',
        '.content-text',
        '#chaptercontent',
        '.showtxt',
    ]

    # 常见的下一页文本
    # “下一章”可能会把下一章内容并入当前章节，因此只匹配明确的分页链接。
    NEXT_PAGE_TEXTS = ['下一页', '下页', '下一页→', 'Next']

    def __init__(self, log_callback: Callable = None, progress_callback: Callable = None,
                 rules_path: str = None, stop_callback: Callable = None):
        self.log = log_callback or print
        self.progress = progress_callback or (lambda x: None)
        self.stop_requested = stop_callback or (lambda: False)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        # 规则持久化 - 保存到exe同目录下的rules.json
        if rules_path is None:
            # 打包成exe后用 sys.executable 的目录
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            rules_path = os.path.join(base_dir, 'rules.json')
        self.rules_path = rules_path
        self.rules = self._load_rules()

        # 当前域名的规则（动态加载）
        self.current_domain = None
        self.chapter_selectors = list(self.DEFAULT_CHAPTER_SELECTORS)
        self.content_selectors = list(self.DEFAULT_CONTENT_SELECTORS)

    def _load_rules(self) -> dict:
        """加载保存的网站规则"""
        if os.path.exists(self.rules_path):
            try:
                with open(self.rules_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_rules(self):
        """保存规则到文件"""
        try:
            with open(self.rules_path, 'w', encoding='utf-8') as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
            self.log("规则已保存")
        except Exception as e:
            self.log(f"保存规则失败: {e}")

    def _get_domain_rules(self, url: str) -> dict:
        """获取指定域名的规则"""
        parsed = urlparse(url)
        return self.rules.get(parsed.netloc, {})

    def _save_domain_rule(self, url: str, key: str, value: str):
        """保存某域名的某条规则"""
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain not in self.rules:
            self.rules[domain] = {}
        self.rules[domain][key] = value
        self._save_rules()
        self.log(f"已保存 {domain} 的规则: {key} = {value}")

    def _get_page(self, url: str, retries: int = 3) -> Optional[str]:
        """获取页面内容；保留 TLS 证书验证，并允许停止重试。"""
        for i in range(retries):
            if self.stop_requested():
                return None
            try:
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding
                return resp.text
            except Exception as e:
                self.log(f"请求失败 (第{i+1}次): {str(e)[:80]}")
                if i + 1 < retries and not self.stop_requested():
                    time.sleep(1)
        return None

    def get_chapter_list(self, catalog_url: str) -> Tuple[List[Tuple[str, str]], str, str]:
        """
        从目录页获取章节列表
        返回: [(章节标题, 章节URL), ...], 书名, 作者
        """
        self.log(f"正在访问目录页: {catalog_url}")
        self.current_domain = urlparse(catalog_url).netloc
        html = self._get_page(catalog_url)
        if not html:
            raise Exception("无法访问目录页")

        soup = BeautifulSoup(html, 'html.parser')

        # 提取书名和作者
        title = self._extract_title(soup)
        author = self._extract_author(soup)
        self.log(f"识别到: 《{title}》 作者: {author}")

        # 加载该域名的已保存规则
        domain_rules = self._get_domain_rules(catalog_url)
        if 'chapter_selector' in domain_rules:
            saved_selector = domain_rules['chapter_selector']
            self.log(f"使用已保存的规则: {saved_selector}")
            self.chapter_selectors = [saved_selector] + self.DEFAULT_CHAPTER_SELECTORS

        base_url = f"{urlparse(catalog_url).scheme}://{urlparse(catalog_url).netloc}"
        chapters = []

        # 尝试内置选择器
        for selector in self.chapter_selectors:
            links = soup.select(selector)
            if links:
                self.log(f"尝试选择器: {selector}")
                temp_chapters = []
                for link in links:
                    text = link.get_text(strip=True)
                    href = link.get('href', '')
                    if text and href and self._is_chapter_title(text):
                        full_url = urljoin(base_url, href)
                        temp_chapters.append((text, full_url))
                if len(temp_chapters) >= 5:  # 找到至少5章才算成功
                    chapters = temp_chapters
                    self.log(f"使用选择器 {selector} 找到 {len(chapters)} 章")
                    # 保存成功的规则
                    self._save_domain_rule(catalog_url, 'chapter_selector', selector)
                    break

        # 如果选择器没找到，自动智能识别
        if not chapters:
            self.log("内置选择器未找到，启动智能识别...")
            chapters = self._auto_detect_chapters(soup, base_url, catalog_url)

        # 如果还是没找到，用正则匹配
        if not chapters:
            self.log("智能识别失败，使用正则匹配")
            chapters = self._extract_chapters_by_regex(html, base_url)

        # 去重
        seen = set()
        unique_chapters = []
        for t, u in chapters:
            if u not in seen:
                seen.add(u)
                unique_chapters.append((t, u))

        self.log(f"共找到 {len(unique_chapters)} 章")
        return unique_chapters, title, author

    def _auto_detect_chapters(self, soup: BeautifulSoup, base_url: str, catalog_url: str) -> List[Tuple[str, str]]:
        """
        自动智能识别章节链接区域
        原理：找到页面中包含最多"第X章"文本的链接容器
        """
        self.log("  分析页面结构，智能识别章节列表...")

        # 获取所有链接
        all_links = soup.find_all('a', href=True)

        # 统计每个父元素下有多少个章节链接
        parent_counts = {}
        for link in all_links:
            text = link.get_text(strip=True)
            if not self._is_chapter_title(text):
                continue

            # 向上找3层父元素
            parent = link.parent
            for _ in range(3):
                if parent is None:
                    break
                # 用元素路径作为key
                path = self._get_element_path(parent)
                parent_counts[path] = parent_counts.get(path, 0) + 1
                parent = parent.parent

        if not parent_counts:
            return []

        # 找到包含最多章节链接的容器
        best_path = max(parent_counts, key=parent_counts.get)
        best_count = parent_counts[best_path]

        if best_count < 3:
            self.log(f"  警告: 最多只找到 {best_count} 个章节链接")
            return []

        self.log(f"  识别到章节容器: {best_path} (包含 {best_count} 章)")

        # 用这个容器下的所有链接
        # 重新找到这个元素
        chapters = []
        # 简化：直接从所有链接中筛选符合条件的
        for link in all_links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            if text and href and self._is_chapter_title(text):
                full_url = urljoin(base_url, href)
                chapters.append((text, full_url))

        # 保存识别到的规则
        # 生成一个CSS选择器
        selector = self._path_to_selector(best_path)
        if selector:
            self._save_domain_rule(catalog_url, 'chapter_selector', selector)

        return chapters

    def _get_element_path(self, elem: Tag) -> str:
        """获取元素的简单路径描述"""
        parts = []
        current = elem
        while current and current.name and len(parts) < 5:
            part = current.name
            if current.get('id'):
                part += f"#{current['id']}"
            elif current.get('class'):
                part += f".{'.'.join(current['class'])}"
            parts.append(part)
            current = current.parent
        return ' > '.join(reversed(parts))

    def _path_to_selector(self, path: str) -> str:
        """把元素路径转成CSS选择器"""
        parts = path.split(' > ')
        # 简化：取最后两部分
        if len(parts) >= 2:
            # 尝试用class选择
            last = parts[-1]
            if '#' in last:
                return f"{last} a"
            elif '.' in last:
                cls = last.split('.')[1]
                return f".{cls} a"
        return None

    def _is_chapter_title(self, text: str) -> bool:
        """判断是否是章节标题"""
        text = text.strip()
        patterns = [
            r'^第\d+章',
            r'^第[一二三四五六七八九十百千]+章',
            r'^第\d+节',
            r'^番外',
            r'^序',
            r'^楔子',
            r'^第一章',
            r'^第二章',
            r'^第\d+章[^\d]',
        ]
        return any(re.match(p, text) for p in patterns)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取书名"""
        meta = soup.find('meta', {'property': 'og:novel:book_name'})
        if meta:
            return meta.get('content', '').strip()

        for selector in ['h1', '.book-name', '.btitle', '#book_name', '.info h2']:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) < 50:
                    return text

        if soup.title:
            title = soup.title.string or ''
            for sep in ['-', '_', '——']:
                if sep in title:
                    parts = title.split(sep)
                    candidate = parts[0].strip()
                    if not re.match(r'^第\d+章', candidate) and len(candidate) > 1:
                        return candidate
        return '未命名小说'

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """提取作者"""
        meta = soup.find('meta', {'property': 'og:novel:author'})
        if meta:
            return meta.get('content', '')
        for tag in soup.find_all(['a', 'span', 'div']):
            text = tag.get_text(strip=True)
            if text.startswith('作者：') or text.startswith('作者:'):
                return text.replace('作者：', '').replace('作者:', '').strip()
        return '未知作者'

    def _extract_chapters_by_regex(self, html: str, base_url: str) -> List[Tuple[str, str]]:
        """用正则表达式提取章节链接"""
        chapters = []
        pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]*第\d+章[^<]*)</a>'
        matches = re.findall(pattern, html, re.IGNORECASE)
        for href, text in matches:
            if self._is_chapter_title(text):
                full_url = urljoin(base_url, href)
                chapters.append((text.strip(), full_url))
        return chapters

    def extract_chapter_content(self, chapter_url: str, chapter_title: str) -> str:
        """
        提取单章完整内容（处理分页）
        返回: 章节完整文本
        """
        all_content = []
        current_url = chapter_url
        page_num = 1
        visited_urls = set()

        while current_url:
            if self.stop_requested():
                break
            if current_url in visited_urls:
                self.log(f"  警告: 检测到重复分页链接，已停止于第{page_num}页")
                break
            visited_urls.add(current_url)
            html = self._get_page(current_url)
            if not html:
                self.log(f"  警告: 第{page_num}页加载失败")
                break

            soup = BeautifulSoup(html, 'html.parser')

            # 提取正文
            content = self._extract_content_from_soup(soup, chapter_url)
            if content:
                lines = content.strip().split('\n')
                body_lines = [l.strip() for l in lines if l.strip()]
                if body_lines and (chapter_title in body_lines[0] or '第' in body_lines[0] and '章' in body_lines[0]):
                    body_lines = body_lines[1:]
                all_content.extend(body_lines)

            # 查找下一页链接
            next_url = self._find_next_page(soup, current_url)
            if next_url and next_url != current_url:
                current_url = next_url
                page_num += 1
                time.sleep(0.3)
            else:
                current_url = None

        return chapter_title + '\n\n' + '\n'.join(all_content)

    def _extract_content_from_soup(self, soup: BeautifulSoup, page_url: str) -> str:
        """从soup中提取正文内容，支持自动识别和OCR"""
        # 先尝试已保存的规则
        domain_rules = self._get_domain_rules(page_url)
        if 'content_selector' in domain_rules:
            saved = domain_rules['content_selector']
            elem = soup.select_one(saved)
            if elem:
                text = elem.get_text('\n', strip=True)
                if len(text) > 100:
                    return text
                # 文字太少，尝试OCR识别图片
                if OCR_AVAILABLE:
                    ocr_text = self._extract_text_from_images(elem, page_url)
                    if len(ocr_text) > 100:
                        self.log("  OCR识别图片正文成功")
                        return ocr_text

        # 尝试内置选择器
        for selector in self.content_selectors:
            elem = soup.select_one(selector)
            if elem:
                text = elem.get_text('\n', strip=True)
                if len(text) > 200:  # 确保是正文
                    # 保存成功的规则
                    self._save_domain_rule(page_url, 'content_selector', selector)
                    return text
                # 文字太少，尝试OCR识别图片
                if OCR_AVAILABLE:
                    ocr_text = self._extract_text_from_images(elem, page_url)
                    if len(ocr_text) > 100:
                        self.log("  OCR识别图片正文成功")
                        return ocr_text

        # 自动智能识别正文区域
        self.log("  内置选择器未找到正文，启动智能识别...")
        content = self._auto_detect_content(soup, page_url)

        # 如果智能识别的文字太少，尝试OCR
        if len(content) < 200 and OCR_AVAILABLE:
            # 找页面上所有大图
            imgs = soup.find_all('img')
            for img in imgs:
                src = img.get('src', '')
                if src and ('content' in src or 'chapter' in src or 'img' in src):
                    ocr_text = self._ocr_image(src, page_url)
                    if len(ocr_text) > 100:
                        self.log("  OCR识别图片正文成功")
                        return ocr_text

        return content

    def _extract_text_from_images(self, elem: Tag, page_url: str) -> str:
        """从元素中的图片提取文字（OCR）"""
        if not OCR_AVAILABLE:
            return ""

        texts = []
        imgs = elem.find_all('img')
        for img in imgs:
            src = img.get('src', '')
            if not src:
                continue
            # 过滤小图标
            width = img.get('width', '0')
            height = img.get('height', '0')
            try:
                if int(width) < 100 or int(height) < 100:
                    continue
            except:
                pass

            text = self._ocr_image(src, page_url)
            if text:
                texts.append(text)

        return '\n'.join(texts)

    def _ocr_image(self, img_url: str, page_url: str) -> str:
        """OCR识别单张图片中的文字（使用RapidOCR）"""
        if not OCR_AVAILABLE:
            return ""

        try:
            # 补全URL
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                parsed = urlparse(page_url)
                img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"

            # 下载图片
            resp = self.session.get(img_url, timeout=10)
            img_bytes = resp.content

            # RapidOCR识别
            ocr = get_ocr()
            result, _ = ocr(img_bytes)

            if result:
                # result格式: [[box, text, score], ...]
                texts = [line[1] for line in result]
                return '\n'.join(texts)
            return ""
        except Exception as e:
            self.log(f"  OCR识别失败: {str(e)[:50]}")
            return ""

    def _auto_detect_content(self, soup: BeautifulSoup, page_url: str) -> str:
        """
        自动识别正文区域
        原理：找页面中文本最多、标签最干净的div
        """
        # 排除导航、侧边栏等元素
        exclude_tags = ['nav', 'header', 'footer', 'aside', 'script', 'style']
        for tag in soup.find_all(exclude_tags):
            tag.decompose()

        # 遍历所有div，计算文本密度
        best_elem = None
        best_score = 0

        for div in soup.find_all(['div', 'article', 'section']):
            text = div.get_text(strip=True)
            # 评分 = 文本长度 / 子元素数量（越干净分越高）
            child_count = len(div.find_all(['a', 'button', 'input']))
            score = len(text) / max(child_count, 1)

            if len(text) > 500 and score > best_score:
                best_score = score
                best_elem = div

        if best_elem:
            text = best_elem.get_text('\n', strip=True)
            # 生成选择器
            selector = self._element_to_selector(best_elem)
            if selector:
                self._save_domain_rule(page_url, 'content_selector', selector)
            return text

        return ''

    def _element_to_selector(self, elem: Tag) -> str:
        """为元素生成一个CSS选择器"""
        if elem.get('id'):
            return f"#{elem['id']}"
        if elem.get('class'):
            return f".{'.'.join(elem['class'][:1])}"  # 只用第一个class
        return None

    def _find_next_page(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """查找下一页链接"""
        # 查找所有链接
        for link in soup.find_all('a'):
            text = link.get_text(strip=True)
            if text in self.NEXT_PAGE_TEXTS:
                href = link.get('href', '')
                if href and href != '#':
                    return urljoin(current_url, href)
        return None

    def validate_content(self, chapters: List[Tuple[str, str]]) -> dict:
        """校验章节内容完整性"""
        total = len(chapters)
        empty = 0
        too_short = 0
        results = []

        for i, (title, content) in enumerate(chapters):
            char_count = len(content)
            issues = []
            if char_count < 200:
                too_short += 1
                issues.append("内容过短")
            if '提取失败' in content or '加载失败' in content:
                empty += 1
                issues.append("提取失败")
            results.append({
                'index': i + 1,
                'title': title,
                'chars': char_count,
                'issues': issues
            })

        return {
            'total': total,
            'empty': empty,
            'too_short': too_short,
            'normal': total - empty - too_short,
            'details': results
        }

    def get_saved_rules(self) -> dict:
        """获取所有已保存的规则"""
        return self.rules
