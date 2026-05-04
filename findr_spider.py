import requests
from bs4 import BeautifulSoup
import json
import time
import os
import logging
from urllib.parse import urlsplit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("findr")

class FindrSpider:
    def __init__(self, seed_urls, max_pages=100, max_per_domain=10):
        self.seed_urls = seed_urls
        self.max_pages = max_pages
        self.max_per_domain = max_per_domain
        self.visited = set()
        self.index = []
        self.domain_counts = {}

    def crawl(self):
        queue = self.seed_urls.copy()
        while queue and len(self.visited) < self.max_pages:
            url = queue.pop(0)
            domain = urlsplit(url).netloc
            if url in self.visited or self.domain_counts.get(domain, 0) >= self.max_per_domain:
                continue
            
            try:
                logger.info(f"Crawling: {url}")
                res = requests.get(url, timeout=5, headers={'User-Agent': 'findr-spider/1.0'})
                if res.status_code != 200: continue
                
                soup = BeautifulSoup(res.text, 'html.parser')
                title = soup.title.string.strip() if soup.title else url
                
                desc = ""
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc: desc = meta_desc.get("content", "").strip()
                
                self.index.append({
                    "title": title,
                    "url": url,
                    "description": desc[:160],
                    "keywords": [w.lower() for w in title.split() if len(w) > 3]
                })

                self.visited.add(url)
                self.domain_counts[domain] = self.domain_counts.get(domain, 0) + 1
                for link in soup.find_all('a', href=True):
                    l_url = link['href']
                    if l_url.startswith('http') and l_url not in self.visited:
                        queue.append(l_url)
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error {url}: {e}")

    def save_sharded_index(self, folder="index"):
        if not os.path.exists(folder): os.makedirs(folder)
        shard_map = {chr(i): [] for i in range(97, 123)}
        shard_map['others'] = []

        for item in self.index:
            chars = set(item['title'][0].lower())
            for kw in item['keywords']: chars.add(kw[0])
            for char in chars:
                target = char if char in shard_map else 'others'
                shard_map[target].append(item)

        for char, data in shard_map.items():
            if data:
                with open(f"{folder}/{char}.json", 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)

if __name__ == "__main__":
    seeds = ["https://news.ycombinator.com/", "https://docs.python.org/3/", "https://atproto.com/"]
    spider = FindrSpider(seeds, max_pages=100)
    spider.crawl()
    spider.save_sharded_index()
