import requests
from bs4 import BeautifulSoup
import random
import time

class BaiduCrawler:
    def __init__(self):
        self.base_url = "https://www.baidu.com/s"
        self.headers = {
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
    def __init__(self):
        self.list_url = "https://sc.news.cn/scyw.htm"
        self.headers = {
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
