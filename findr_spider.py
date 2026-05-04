import requests
from bs4 import BeautifulSoup
import json
import time
import os
import logging
from urllib.parse import urlsplit

# Configure logging to track crawl progress in GitHub Actions console
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("findr")

class FindrSpider:
    def __init__(self, seed_urls, max_pages=500, max_per_domain=15):
        self.seed_urls = seed_urls
        self.max_pages = max_pages
        self.max_per_domain = max_per_domain
        self.visited = set()
        self.index = []
        self.domain_counts = {}

    def crawl(self):
        """
        Executes a Breadth-First Search crawl. 
        Respects domain limits to ensure variety and prevents infinite loops.
        """
        queue = self.seed_urls.copy()
        logger.info(f"Starting crawl. Target: {self.max_pages} pages.")
        
        while queue and len(self.visited) < self.max_pages:
            url = queue.pop(0)
            domain = urlsplit(url).netloc
            
            # Skip if already indexed or if the domain has been sampled enough
            if url in self.visited or self.domain_counts.get(domain, 0) >= self.max_per_domain:
                continue
            
            try:
                logger.info(f"Indexing: {url}")
                # Set a custom User-Agent to identify the crawler
                res = requests.get(url, timeout=5, headers={'User-Agent': 'findr-spider/1.1'})
                if res.status_code != 200: continue
                
                soup = BeautifulSoup(res.text, 'html.parser')
                title = soup.title.string.strip() if soup.title else url
                
                # Extract meta description for the search snippet
                desc = ""
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc: desc = meta_desc.get("content", "").strip()
                
                # Populate the local index list
                self.index.append({
                    "title": title,
                    "url": url,
                    "description": desc[:180],
                    "keywords": [w.lower() for w in title.split() if len(w) > 3]
                })

                self.visited.add(url)
                self.domain_counts[domain] = self.domain_counts.get(domain, 0) + 1
                
                # Discover new links on the page for future crawling
                for link in soup.find_all('a', href=True):
                    l_url = link['href']
                    if l_url.startswith('http') and l_url not in self.visited:
                        queue.append(l_url)
                
                # 1-second delay to be respectful to host servers
                time.sleep(1)
            except Exception as e:
                logger.error(f"Failed to process {url}: {e}")

    def save_sharded_index(self, folder="index"):
        """
        Distributes the index into alphabetical shards (a.json, b.json, etc.).
        This allows the frontend to fetch only the data relevant to the first letter 
        of a search query, minimizing network payload.
        """
        if not os.path.exists(folder): os.makedirs(folder)
        shard_map = {chr(i): [] for i in range(97, 123)}
        shard_map['others'] = []

        for item in self.index:
            # Associate item with shards based on the first letter of title and keywords
            chars = set(item['title'][0].lower())
            for kw in item['keywords']: 
                if kw: chars.add(kw[0])
            
            for char in chars:
                target = char if char in shard_map else 'others'
                shard_map[target].append(item)

        # Write each shard to disk as a JSON file
        for char, data in shard_map.items():
            if data:
                # Remove duplicate entries within the same shard
                seen = set()
                unique = [x for x in data if not (x['url'] in seen or seen.add(x['url']))]
                with open(f"{folder}/{char}.json", 'w', encoding='utf-8') as f:
                    json.dump(unique, f, ensure_ascii=False)
        logger.info("Indexing and sharding complete.")

if __name__ == "__main__":
    # Diverse seeds covering tech, news, reference, and web culture
    seeds = [
        "https://news.ycombinator.com/", "https://github.com/explore", "https://tldr.tech/",
        "https://www.reuters.com/", "https://www.npr.org/", "https://www.theatlantic.com/",
        "https://en.wikipedia.org/wiki/Portal:Contents", "https://archive.org/details/texts",
        "https://neocities.org/browse", "https://wiby.me/", "https://68k.news/"
    ]
    spider = FindrSpider(seeds)
    spider.crawl()
    spider.save_sharded_index()
