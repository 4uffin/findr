import requests
from bs4 import BeautifulSoup
import json
import time
import os
import logging
from urllib.parse import urlsplit

# Configure logging for the GitHub Actions console
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
        """Orchestrates the BFS crawl starting from seed URLs."""
        queue = self.seed_urls.copy()
        while queue and len(self.visited) < self.max_pages:
            url = queue.pop(0)
            domain = urlsplit(url).netloc
            
            # Skip if already visited or if we've hit the per-domain limit
            if url in self.visited or self.domain_counts.get(domain, 0) >= self.max_per_domain:
                continue
            
            try:
                logger.info(f"Crawling: {url}")
                res = requests.get(url, timeout=5, headers={'User-Agent': 'findr-spider/1.0'})
                if res.status_code != 200: continue
                
                soup = BeautifulSoup(res.text, 'html.parser')
                title = soup.title.string.strip() if soup.title else url
                
                # Extract meta description for search snippets
                desc = ""
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc: desc = meta_desc.get("content", "").strip()
                
                # Build the search object
                self.index.append({
                    "title": title,
                    "url": url,
                    "description": desc[:160],
                    "keywords": [w.lower() for w in title.split() if len(w) > 3]
                })

                self.visited.add(url)
                self.domain_counts[domain] = self.domain_counts.get(domain, 0) + 1
                
                # Find outbound links for discovery
                for link in soup.find_all('a', href=True):
                    l_url = link['href']
                    if l_url.startswith('http') and l_url not in self.visited:
                        queue.append(l_url)
                
                # Politeness delay to avoid IP blocks
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error crawling {url}: {e}")

    def save_sharded_index(self, folder="index"):
        """Distributes data into A-Z shards for fast frontend retrieval."""
        if not os.path.exists(folder): os.makedirs(folder)
        shard_map = {chr(i): [] for i in range(97, 123)}
        shard_map['others'] = []

        for item in self.index:
            # Map item to multiple shards based on title and keywords
            chars = set(item['title'][0].lower())
            for kw in item['keywords']: chars.add(kw[0])
            
            for char in chars:
                target = char if char in shard_map else 'others'
                shard_map[target].append(item)

        # Write shards to disk as JSON
        for char, data in shard_map.items():
            if data:
                # Deduplicate entries in the same shard
                seen = set()
                unique = [x for x in data if not (x['url'] in seen or seen.add(x['url']))]
                with open(f"{folder}/{char}.json", 'w', encoding='utf-8') as f:
                    json.dump(unique, f, ensure_ascii=False)

if __name__ == "__main__":
    # Core technical seeds for the index
    seeds = ["https://news.ycombinator.com/", "https://docs.python.org/3/", "https://atproto.com/"]
    spider = FindrSpider(seeds, max_pages=100)
    spider.crawl()
    spider.save_sharded_index()
