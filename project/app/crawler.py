import requests
from bs4 import BeautifulSoup
import random
import time

_CRAWLER_REGISTRY = {}

def register_crawler(key, cls):
    _CRAWLER_REGISTRY[key] = cls

def create_crawler(key, config=None):
    cls = _CRAWLER_REGISTRY.get(key)
    if cls:
        try:
            return cls(config=config)
        except TypeError:
            return cls()
    # fallback: unknown key
    k = (key or '').strip().lower()
    if k in ['sina','新浪','新浪网']:
        return SinaCrawler(config=config)
    if k in ['xinhua','新华','新华网','news.cn','xinhuanet']:
        return XinhuaCrawler(config=config)
    if k in ['ifeng','凤凰','凤凰网']:
        return IfengCrawler(config=config)
    raise ValueError(f"未注册的爬虫 key: {key}")

class BaiduCrawler:
    def __init__(self, config=None):
        cfg = config or {}
        self.base_url = cfg.get('base_url') or "https://www.baidu.com/s"
        self.headers = cfg.get('headers') or {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 更新 Cookie 以避免被识别为机器人
            "Cookie": "BIDUPSID=D48AC21A701043225723F7B0416A45A5; PSTM=1749868400; BAIDUID=D48AC21A70104322974B66FAE2F73383:FG=1; BD_UPN=12314753; H_PS_PSSID=60272_63144_66104_66109_66213; BD_CK_SAM=1; PSINO=6; H_WISE_SIDS=60272_63144_66104_66109_66213;",
            "Host": "www.baidu.com",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": "\"Not)A;Brand\";v=\"24\", \"Chromium\";v=\"116\"",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": "\"Windows\"",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.97 Safari/537.36"
        }

    def fetch_data(self, keyword, max_count=30):
        # 空关键词时使用默认词，保证可输出
        if not (keyword or '').strip():
            keyword = '新闻'
        all_results = []
        page = 0
        
        while len(all_results) < max_count:
            pn = page * 10
            print(f"Fetching page {page + 1} (pn={pn})...")
            
            params = {
                "rtt": "1",
                "bsst": "1",
                "cl": "2",
                "tn": "news",
                "rsv_dl": "ns_pc",
                "word": keyword,
                "pn": str(pn)
            }
            
            try:
                response = requests.get(
                    self.base_url, 
                    headers=self.headers, 
                    params=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    # 调试：保存HTML到文件以分析结构
                    # with open(f"debug_baidu_{page}.html", "w", encoding="utf-8") as f:
                    #     f.write(response.text)
                    
                    new_results = self.parse_html(response.text)
                    new_results = self.clean_results(new_results)
                    if not new_results:
                        print("No more results found on this page.")
                        break
                        
                    all_results.extend(new_results)
                    print(f"Found {len(new_results)} items on page {page + 1}. Total: {len(all_results)}")
                    
                    if len(new_results) < 5: # 如果一页少于5条，可能没数据了
                         print("Results count too low, stopping pagination.")
                         break
                         
                else:
                    print(f"Error: Status code {response.status_code}")
                    break
                    
            except Exception as e:
                print(f"Exception occurred: {e}")
                break
            
            page += 1
            time.sleep(random.uniform(1, 2)) # 随机延迟，避免被封
            
            if page >= 5: # 安全限制，最多翻5页
                print("Reached maximum page limit (5).")
                break
                
        return all_results[:max_count]

    def iter_data(self, keyword, max_count=30):
        # 逐条迭代返回，便于SSE实时推送
        if not (keyword or '').strip():
            keyword = '新闻'
        count = 0
        page = 0
        while count < max_count:
            pn = page * 10
            params = {"rtt":"1","bsst":"1","cl":"2","tn":"news","rsv_dl":"ns_pc","word":keyword,"pn":str(pn)}
            try:
                response = requests.get(self.base_url, headers=self.headers, params=params, timeout=10)
                if response.status_code != 200:
                    break
                items = self.parse_html(response.text)
                items = self.clean_results(items)
                if not items:
                    break
                for it in items:
                    yield it
                    count += 1
                    if count >= max_count:
                        break
            except Exception:
                break
            page += 1
            time.sleep(random.uniform(1, 2))
            if page >= 5:
                break

    def parse_html(self, html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        results = []
        
        # Use the robust selector for items
        items = soup.select('div.result-op.c-container')
        if not items:
            # Fallback
            items = soup.select('.c-container')
        
        print(f"Found {len(items)} potential items")
        
        for item in items:
            try:
                # Title: h3 > a
                title_elem = item.select_one('h3 a')
                if not title_elem:
                    continue 
                
                title = title_elem.get_text(strip=True)
                original_url = title_elem.get('href', '')
                
                # Summary: Look for aria-label starting with "摘要"
                summary_elem = item.select_one('span[aria-label^="摘要"]')
                if summary_elem:
                    summary = summary_elem.get_text(strip=True)
                else:
                    # Fallback to finding text in a likely container
                    text_container = item.select_one('.c-span-last')
                    if text_container:
                        summary = text_container.get_text(strip=True)
                    else:
                        summary = "无概要"

                # Source: Look for aria-label starting with "新闻来源"
                source_elem = item.select_one('span[aria-label^="新闻来源"]')
                if source_elem:
                    source = source_elem.get_text(strip=True)
                else:
                    # Fallback
                    source_elem = item.select_one('.c-color-gray')
                    source = source_elem.get_text(strip=True) if source_elem else "未知来源"
                
                # Cover Image
                # Find img that is NOT the source icon
                images = item.select('img')
                cover_img = ""
                for img in images:
                    # Check if it's a source icon by checking parent classes
                    is_source_icon = False
                    parent = img.parent
                    # Check up to 3 levels up
                    for _ in range(3):
                        if not parent: break
                        classes = parent.get('class', [])
                        if any('news-source' in c or 'source-icon' in c for c in classes):
                            is_source_icon = True
                            break
                        parent = parent.parent
                    
                    if is_source_icon:
                        continue
                        
                    src = img.get('src', '')
                    if src:
                        cover_img = src
                        break # Take the first valid non-source image
                
                if not title or title == "无标题":
                    continue

                result = {
                    "title": title,
                    "summary": summary,
                    "cover": cover_img,
                    "original_url": original_url,
                    "source": source
                }
                results.append(result)
                
            except Exception as e:
                print(f"Error parsing item: {e}")
                continue
                
        return results

    def sanitize_text(self, text):
        if not text:
            return ""
        t = str(text)
        t = t.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
        t = ' '.join(t.split())
        return t.strip()

    def is_noise_text(self, text):
        if not text:
            return True
        t = self.sanitize_text(text)
        if len(t) < 6:
            return True
        import re
        valid = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", t)
        ratio = (len(valid) / max(len(t), 1))
        if ratio < 0.4:
            return True
        return False

    def clean_results(self, items):
        cleaned = []
        seen = set()
        for it in items:
            title = self.sanitize_text(it.get('title', ''))
            summary = self.sanitize_text(it.get('summary', ''))
            source = self.sanitize_text(it.get('source', ''))
            cover = (it.get('cover') or '').strip()
            url = (it.get('original_url') or '').strip()

            if self.is_noise_text(title):
                continue
            if self.is_noise_text(summary):
                summary = '无概要'
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)

            if not (url.startswith('http://') or url.startswith('https://')):
                url = ''
            if not (cover.startswith('http://') or cover.startswith('https://')):
                cover = ''
            if not cover:
                cover = self.default_cover()
            cleaned.append({
                'title': title,
                'summary': summary,
                'cover': cover,
                'original_url': url,
                'source': source or '未知来源'
            })
        return cleaned

    def default_cover(self):
        return 'https://dummyimage.com/242x162/18202D/ffffff&text=NEWS'

    def to_display_schema(self, items):
        formatted = []
        for it in items:
            formatted.append({
                'original_url': it.get('original_url') or '',
                'cover': it.get('cover') or '',
                'source': it.get('source') or '',
                'title': it.get('title') or '',
                'summary': it.get('summary') or ''
            })
        return formatted

if __name__ == "__main__":
    # 测试代码
    crawler = BaiduCrawler()
    data = crawler.fetch_data("成都")
    print(f"Total valid items: {len(data)}")
    for idx, item in enumerate(data):
        print(f"[{idx+1}] {item['title']}")
        print(f"    来源: {item['source']}")
        print("-" * 50)
class XinhuaCrawler:
    def __init__(self, config=None):
        cfg = config or {}
        self.list_url = cfg.get('list_url') or "https://sc.news.cn/scyw.htm"
        self.headers = cfg.get('headers') or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }

    def fetch_data(self, keyword='', max_count=30):
        import requests, re
        try:
            items = []
            # 始终先尝试频道列表，兼容关键字过滤
            try:
                r = requests.get(self.list_url, headers=self.headers, timeout=12)
                if r.status_code == 200:
                    raw = r.content
                    enc = (r.encoding or '').lower()
                    if not enc:
                        m = re.search(rb'charset=([a-zA-Z0-9_-]+)', raw[:8192], re.I)
                        if m:
                            try:
                                enc = m.group(1).decode('ascii', 'ignore').lower()
                            except Exception:
                                enc = ''
                    if not enc:
                        try:
                            enc = (getattr(r, 'apparent_encoding', '') or '').lower()
                        except Exception:
                            enc = ''
                    html = ''
                    for e in [enc, 'utf-8', 'gb18030', 'gbk', 'gb2312']:
                        if not e:
                            continue
                        try:
                            html = raw.decode(e, errors='ignore')
                            break
                        except Exception:
                            continue
                    if not html:
                        html = raw.decode('utf-8', errors='ignore')
                    parsed = self.parse_html(html)
                    if keyword and keyword.strip():
                        kw = keyword.strip()
                        parsed = [it for it in parsed if (kw in it.get('title','')) or (kw in it.get('summary',''))]
                    items.extend(parsed)
            except Exception:
                pass
            # 站点搜索作为补充，避免列表页面结构变化无结果
            try:
                bc = BaiduCrawler()
                k = (keyword or '').strip()
                items.extend(bc.fetch_data(f"site:news.cn {k}".strip()) or [])
                items.extend(bc.fetch_data(f"site:xinhuanet.com {k}".strip()) or [])
            except Exception:
                pass
            items = self.clean_results(items)
            return items[:max_count]
        except Exception:
            return []

    def iter_data(self, keyword='', max_count=30):
        # 逐条迭代返回，便于SSE实时推送
        import requests, re
        sent = 0
        try:
            # 频道列表优先
            try:
                r = requests.get(self.list_url, headers=self.headers, timeout=12)
                if r.status_code == 200:
                    raw = r.content
                    enc = (r.encoding or '').lower()
                    if not enc:
                        m = re.search(rb'charset=([a-zA-Z0-9_-]+)', raw[:8192], re.I)
                        if m:
                            try:
                                enc = m.group(1).decode('ascii', 'ignore').lower()
                            except Exception:
                                enc = ''
                    html = ''
                    for e in [enc, 'utf-8', 'gb18030', 'gbk', 'gb2312']:
                        if not e:
                            continue
                        try:
                            html = raw.decode(e, errors='ignore')
                            break
                        except Exception:
                            continue
                    if not html:
                        html = raw.decode('utf-8', errors='ignore')
                    parsed = self.parse_html(html)
                    if keyword and keyword.strip():
                        kw = keyword.strip()
                        parsed = [it for it in parsed if (kw in it.get('title','')) or (kw in it.get('summary',''))]
                    cleaned = self.clean_results(parsed)
                    for it in cleaned:
                        yield it
                        sent += 1
                        if sent >= max_count:
                            return
            except Exception:
                pass
            # 站点搜索补充
            try:
                bc = BaiduCrawler()
                for it in bc.iter_data(f"site:news.cn {keyword}".strip(), max_count=max_count - sent):
                    yield it
                    sent += 1
                    if sent >= max_count:
                        return
                for it in bc.iter_data(f"site:xinhuanet.com {keyword}".strip(), max_count=max_count - sent):
                    yield it
                    sent += 1
                    if sent >= max_count:
                        return
            except Exception:
                return
        except Exception:
            return

    def parse_html(self, html):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        results = []
        items = soup.select('div.scpd_page_box li') or soup.select('li')
        for li in items:
            try:
                a = li.find('a')
                if not a:
                    continue
                url = a.get('href') or ''
                if url.startswith('//'):
                    url = 'https:' + url
                if url.startswith('/'):
                    url = 'https://sc.news.cn' + url
                title = ''
                for sel in ['dt', 'h3', 'span', 'a']:
                    n = li.find(sel)
                    if n:
                        title = n.get_text(strip=True)
                        if title:
                            break
                dd = li.find('dd') or li.find('p')
                summary = dd.get_text(strip=True) if dd else ''
                img = li.find('img', class_='scpd_auto_pic') or li.find('img')
                cover = ''
                if img:
                    src = img.get('src') or img.get('data-src') or ''
                    if src.startswith('/'):
                        src = 'https://sc.news.cn' + src
                    if src.startswith('//'):
                        src = 'https:' + src
                    cover = src
                results.append({
                    'title': title or a.get_text(strip=True),
                    'summary': summary or '无概要',
                    'cover': cover,
                    'original_url': url,
                    'source': '新华网'
                })
            except Exception:
                continue
        return results

    def sanitize_text(self, text):
        if not text:
            return ""
        t = str(text)
        t = t.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '')
        t = ' '.join(t.split())
        return t.strip()

    def is_noise_text(self, text):
        if not text:
            return True
        t = self.sanitize_text(text)
        if len(t) < 4:
            return True
        import re
        valid = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", t)
        ratio = (len(valid) / max(len(t), 1))
        if ratio < 0.4:
            return True
        return False

    def default_cover(self):
        return 'https://dummyimage.com/242x162/18202D/ffffff&text=NEWS'

    def clean_results(self, items):
        cleaned = []
        seen = set()
        for it in items:
            title = self.sanitize_text(it.get('title', ''))
            summary = self.sanitize_text(it.get('summary', ''))
            source = self.sanitize_text(it.get('source', ''))
            cover = (it.get('cover') or '').strip()
            url = (it.get('original_url') or '').strip()
            if self.is_noise_text(title):
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            if not (url.startswith('http://') or url.startswith('https://')):
                url = ''
            if not (cover.startswith('http://') or cover.startswith('https://')):
                cover = ''
            if not cover:
                cover = self.default_cover()
            cleaned.append({
                'title': title,
                'summary': summary if not self.is_noise_text(summary) else '无概要',
                'cover': cover,
                'original_url': url,
                'source': source or '新华网'
            })
        return cleaned

    def to_display_schema(self, items):
        formatted = []
        for it in items:
            formatted.append({
                'original_url': it.get('original_url') or '',
                'cover': it.get('cover') or '',
                'source': it.get('source') or '',
                'title': it.get('title') or '',
                'summary': it.get('summary') or ''
            })
        return formatted

# 注册内置爬虫
register_crawler('baidu', BaiduCrawler)
register_crawler('xinhua', XinhuaCrawler)
class SinaCrawler:
    def __init__(self, config=None):
        cfg = config or {}
        self.api = cfg.get('api') or 'https://feed.mix.sina.com.cn/api/roll/get'
        self.pageid = int(cfg.get('pageid') or 153)
        self.lid = int(cfg.get('lid') or 2509)
        self.headers = cfg.get('headers') or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }

    def fetch_data(self, keyword='', max_count=30):
        import requests
        results = []
        page = 1
        kw = (keyword or '').strip()
        try:
            while len(results) < max_count and page <= 5:
                params = {
                    'pageid': str(self.pageid),
                    'lid': str(self.lid),
                    'num': str(min(50, max_count - len(results))),
                    'page': str(page)
                }
                r = requests.get(self.api, headers=self.headers, params=params, timeout=12)
                if r.status_code != 200:
                    break
                js = {}
                try:
                    js = r.json() or {}
                except Exception:
                    break
                data = (js.get('result') or {}).get('data') or []
                if not isinstance(data, list) or not data:
                    break
                for it in data:
                    title = (it.get('title') or '').strip()
                    intro = (it.get('intro') or '').strip()
                    url = (it.get('url') or '').strip()
                    # 放宽过滤：关键词命中标题或简介；无关键词不过滤
                    if kw:
                        if (kw not in title) and (kw not in intro):
                            continue
                    images = it.get('images') or []
                    cover = ''
                    if isinstance(images, list) and images:
                        c = images[0]
                        cover = (c.get('img_url') or '').strip()
                    results.append({
                        'title': title or '无标题',
                        'summary': intro or '无概要',
                        'cover': cover,
                        'original_url': url,
                        'source': (it.get('media_name') or '新浪网').strip() or '新浪网'
                    })
                    if len(results) >= max_count:
                        break
                page += 1
        except Exception:
            pass
        cleaned = self.clean_results(results)
        # 若频道未命中关键词或无数据，回退到站点搜索
        if not cleaned:
            try:
                bc = BaiduCrawler()
                cleaned = bc.fetch_data(f"site:sina.com.cn {kw}".strip(), max_count=max_count) or []
            except Exception:
                cleaned = []
        return cleaned[:max_count]

    def iter_data(self, keyword='', max_count=30):
        import requests
        count = 0
        page = 1
        kw = (keyword or '').strip()
        try:
            while count < max_count and page <= 5:
                params = {
                    'pageid': str(self.pageid),
                    'lid': str(self.lid),
                    'num': str(min(50, max_count - count)),
                    'page': str(page)
                }
                r = requests.get(self.api, headers=self.headers, params=params, timeout=12)
                if r.status_code != 200:
                    break
                js = {}
                try:
                    js = r.json() or {}
                except Exception:
                    break
                data = (js.get('result') or {}).get('data') or []
                if not isinstance(data, list) or not data:
                    break
                for it in data:
                    title = (it.get('title') or '').strip()
                    intro = (it.get('intro') or '').strip()
                    if kw and (kw not in title) and (kw not in intro):
                        continue
                    images = it.get('images') or []
                    cover = ''
                    if isinstance(images, list) and images:
                        c = images[0]
                        cover = (c.get('img_url') or '').strip()
                    yield {
                        'title': title or '无标题',
                        'summary': intro or '无概要',
                        'cover': cover,
                        'original_url': (it.get('url') or '').strip(),
                        'source': (it.get('media_name') or '新浪网').strip() or '新浪网'
                    }
                    count += 1
                    if count >= max_count:
                        return
                page += 1
            # 若无数据，回退站点搜索
            if count == 0:
                try:
                    bc = BaiduCrawler()
                    for it in bc.iter_data(f"site:sina.com.cn {kw}".strip(), max_count=max_count):
                        yield it
                except Exception:
                    return
        except Exception:
            return

    def sanitize_text(self, text):
        if not text:
            return ''
        t = str(text)
        t = t.replace('\u200b','').replace('\u200c','').replace('\u200d','')
        t = ' '.join(t.split())
        return t.strip()

    def is_noise_text(self, text):
        if not text:
            return True
        t = self.sanitize_text(text)
        if len(t) < 4:
            return True
        import re
        valid = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", t)
        ratio = (len(valid) / max(len(t), 1))
        if ratio < 0.4:
            return True
        return False

    def default_cover(self):
        return 'https://dummyimage.com/242x162/18202D/ffffff&text=NEWS'

    def clean_results(self, items):
        cleaned = []
        seen = set()
        for it in items:
            title = self.sanitize_text(it.get('title',''))
            summary = self.sanitize_text(it.get('summary',''))
            source = self.sanitize_text(it.get('source',''))
            cover = (it.get('cover') or '').strip()
            url = (it.get('original_url') or '').strip()
            if self.is_noise_text(title):
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            if not (url.startswith('http://') or url.startswith('https://')):
                url = ''
            if not (cover.startswith('http://') or cover.startswith('https://')):
                cover = ''
            if not cover:
                cover = self.default_cover()
            cleaned.append({
                'title': title,
                'summary': summary if not self.is_noise_text(summary) else '无概要',
                'cover': cover,
                'original_url': url,
                'source': source or '新浪网'
            })
        return cleaned

    def to_display_schema(self, items):
        formatted = []
        for it in items:
            formatted.append({
                'original_url': it.get('original_url') or '',
                'cover': it.get('cover') or '',
                'source': it.get('source') or '新浪网',
                'title': it.get('title') or '',
                'summary': it.get('summary') or ''
            })
        return formatted

register_crawler('sina', SinaCrawler)

def _resolve_final(url, headers=None):
    try:
        if not url:
            return ''
        import requests
        r = requests.get(url, headers=headers or {}, timeout=8, allow_redirects=True)
        return (r.url or url)
    except Exception:
        return url

class IfengCrawler:
    def __init__(self, config=None):
        cfg = config or {}
        self.headers = cfg.get('headers') or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }

    def fetch_data(self, keyword='', max_count=30):
        import requests
        from bs4 import BeautifulSoup
        kw = (keyword or '').strip()
        results = []
        try:
            if kw:
                url = f"https://so.ifeng.com/?q={kw}"
            else:
                url = "https://news.ifeng.com/"
            r = requests.get(url, headers=self.headers, timeout=12)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text or '', 'html.parser')
                anchors = soup.select('a')
                for a in anchors:
                    href = (a.get('href') or '').strip()
                    if not href:
                        continue
                    if 'ifeng.com' not in href:
                        continue
                    title = a.get_text(strip=True) or ''
                    if not title or len(title) < 6:
                        continue
                    results.append({
                        'title': title,
                        'summary': '无概要',
                        'cover': '',
                        'original_url': href,
                        'source': '凤凰网'
                    })
                    if len(results) >= max_count:
                        break
        except Exception:
            results = []
        if results:
            return self.clean_results(results)[:max_count]
        bc = BaiduCrawler({'headers': self.headers})
        q = f"site:ifeng.com {keyword}".strip()
        items = bc.fetch_data(q, max_count=max_count) or []
        fixed = []
        for it in items:
            u = (it.get('original_url') or '').strip()
            u2 = _resolve_final(u, headers=self.headers) if 'baidu.com' in u else u
            src = '凤凰网' if 'ifeng.com' in (u2 or '') else (it.get('source') or '凤凰网')
            fixed.append({
                'title': it.get('title') or '',
                'summary': it.get('summary') or '无概要',
                'cover': it.get('cover') or '',
                'original_url': u2,
                'source': src
            })
            if len(fixed) >= max_count:
                break
        return bc.clean_results(fixed)[:max_count]

    def iter_data(self, keyword='', max_count=30):
        import requests
        from bs4 import BeautifulSoup
        kw = (keyword or '').strip()
        count = 0
        try:
            if kw:
                url = f"https://so.ifeng.com/?q={kw}"
            else:
                url = "https://news.ifeng.com/"
            r = requests.get(url, headers=self.headers, timeout=12)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text or '', 'html.parser')
                anchors = soup.select('a')
                for a in anchors:
                    href = (a.get('href') or '').strip()
                    if not href:
                        continue
                    if 'ifeng.com' not in href:
                        continue
                    title = a.get_text(strip=True) or ''
                    if not title or len(title) < 6:
                        continue
                    yield {
                        'title': title,
                        'summary': '无概要',
                        'cover': '',
                        'original_url': href,
                        'source': '凤凰网'
                    }
                    count += 1
                    if count >= max_count:
                        return
        except Exception:
            pass
        bc = BaiduCrawler({'headers': self.headers})
        q = f"site:ifeng.com {keyword}".strip()
        for it in bc.iter_data(q, max_count=max_count - count):
            u = (it.get('original_url') or '').strip()
            u2 = _resolve_final(u, headers=self.headers) if 'baidu.com' in u else u
            src = '凤凰网' if 'ifeng.com' in (u2 or '') else (it.get('source') or '凤凰网')
            yield {
                'title': it.get('title') or '',
                'summary': it.get('summary') or '无概要',
                'cover': it.get('cover') or '',
                'original_url': u2,
                'source': src
            }
            count += 1
            if count >= max_count:
                return

    def to_display_schema(self, items):
        formatted = []
        for it in items:
            formatted.append({
                'original_url': it.get('original_url') or '',
                'cover': it.get('cover') or '',
                'source': it.get('source') or '凤凰网',
                'title': it.get('title') or '',
                'summary': it.get('summary') or ''
            })
        return formatted

register_crawler('ifeng', IfengCrawler)
