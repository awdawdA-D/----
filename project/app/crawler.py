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

if __name__ == "__main__":
    # 测试代码
    crawler = BaiduCrawler()
    data = crawler.fetch_data("成都")
    print(f"Total valid items: {len(data)}")
    for idx, item in enumerate(data):
        print(f"[{idx+1}] {item['title']}")
        print(f"    来源: {item['source']}")
        print("-" * 50)
