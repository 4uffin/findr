import asyncio
import aiohttp
import async_timeout
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urlunparse
import json
import os
import logging
import time
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("findr-async")


class AsyncFindrCrawler:
    def __init__(self, seed_urls, *, max_pages=500, max_per_domain=5, concurrency=20, max_retries=3, user_agent="findr-async/1.0 (+https://github.com/4uffin/findr)"):
        self.seed_urls = seed_urls
        self.max_pages = max_pages
        self.max_per_domain = max_per_domain
        self.visited = set()
        self.index = []
        self.domain_counts = defaultdict(int)
        self.queue = asyncio.Queue()
        self.robots = {}  # domain -> parsed robots (lines)
        self.domain_semaphores = {}  # domain -> asyncio.Semaphore
        self.session = None
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.user_agent = user_agent
        # simple per-domain crawl-delay (seconds); default None
        self.crawl_delays = {}

    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(headers={'User-Agent': self.user_agent})

    async def fetch_robots(self, domain):
        # Fetch robots.txt and keep simple directives for user-agent '*'
        if domain in self.robots:
            return self.robots[domain]
        await self._ensure_session()
        robots_url = f"https://{domain}/robots.txt"
        try:
            async with async_timeout.timeout(10):
                async with self.session.get(robots_url) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        lines = [ln.strip() for ln in text.splitlines()]
                        self.robots[domain] = lines
                        # try to parse Crawl-delay for * or find a number on a line
                        delay = None
                        ua = None
                        for ln in lines:
                            if ln.lower().startswith('user-agent:'):
                                ua = ln.split(':', 1)[1].strip()
                            if ln.lower().startswith('crawl-delay:') and (ua == '*' or ua is None):
                                try:
                                    delay = float(ln.split(':', 1)[1].strip())
                                    self.crawl_delays[domain] = delay
                                    break
                                except ValueError:
                                    pass
                        return lines
        except Exception:
            pass
        self.robots[domain] = []
        return []

    def is_allowed_by_robots(self, domain, path):
        # Very small and conservative robots.txt check: disallow if a "Disallow: <path>" line matches prefix
        lines = self.robots.get(domain, [])
        if not lines:
            return True
        allowed = True
        ua = None
        relevant = False
        for ln in lines:
            if ln.lower().startswith('user-agent:'):
                ua = ln.split(':', 1)[1].strip()
                relevant = (ua == '*' or ua.lower() in self.user_agent.lower())
            if not relevant:
                continue
            if ln.lower().startswith('disallow:'):
                pathpat = ln.split(':', 1)[1].strip()
                if pathpat == '':
                    continue
                if path.startswith(pathpat):
                    allowed = False
                    break
        return allowed

    def normalize_url(self, base, link):
        # Resolve relative URLs, remove fragments, normalize scheme/host, remove default ports
        try:
            joined = urljoin(base, link)
            p = urlparse(joined)
            scheme = p.scheme.lower() or 'http'
            netloc = p.netloc.lower()
            # strip default ports
            if netloc.endswith(':80') and scheme == 'http':
                netloc = netloc[:-3]
            if netloc.endswith(':443') and scheme == 'https':
                netloc = netloc[:-4]
            path = p.path or '/'
            # remove fragments
            normalized = urlunparse((scheme, netloc, path, '', p.query, ''))
            return normalized
        except Exception:
            return None

    async def fetch(self, url, domain):
        await self._ensure_session()
        sem = self.domain_semaphores.setdefault(domain, asyncio.Semaphore(self.max_per_domain))
        async with sem:
            # honor crawl-delay if present
            delay = self.crawl_delays.get(domain)
            if delay:
                await asyncio.sleep(delay)
            last_exc = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    async with async_timeout.timeout(10):
                        async with self.session.get(url) as resp:
                            if resp.status != 200:
                                return None
                            text = await resp.text()
                            return text
                except Exception as e:
                    last_exc = e
                    backoff = min(2 ** attempt, 10)
                    await asyncio.sleep(backoff)
            logger.debug(f"Failed fetch {url}: {last_exc}")
            return None

    async def worker(self):
        while len(self.visited) < self.max_pages:
            try:
                url = await asyncio.wait_for(self.queue.get(), timeout=5)
            except asyncio.TimeoutError:
                break
            if url in self.visited:
                self.queue.task_done()
                continue
            domain = urlparse(url).netloc
            if self.domain_counts[domain] >= self.max_per_domain:
                self.queue.task_done()
                continue

            # Ensure robots for this domain
            await self.fetch_robots(domain)
            path = urlparse(url).path
            if not self.is_allowed_by_robots(domain, path):
                logger.info(f"Blocked by robots.txt: {url}")
                self.queue.task_done()
                continue

            logger.info(f"Crawling: {url}")
            html = await self.fetch(url, domain)
            if not html:
                self.queue.task_done()
                continue

            try:
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.title.string.strip() if soup.title and soup.title.string else url
                meta_desc_tag = soup.find('meta', attrs={'name': 'description'})
                desc = meta_desc_tag.get('content', '').strip() if meta_desc_tag else ''
                keywords = [w.lower() for w in title.split() if len(w) > 3]

                item = {
                    'title': title,
                    'url': url,
                    'description': desc[:180],
                    'keywords': keywords,
                }
                self.index.append(item)
                self.visited.add(url)
                self.domain_counts[domain] += 1

                # discover links
                for a in soup.find_all('a', href=True):
                    l = a['href']
                    n = self.normalize_url(url, l)
                    if not n:
                        continue
                    if n in self.visited:
                        continue
                    # small guard: only HTTP/S
                    parsed = urlparse(n)
                    if parsed.scheme not in ('http', 'https'):
                        continue
                    # check robots allow quickly if we already fetched
                    dom = parsed.netloc
                    r = self.robots.get(dom)
                    if r is not None:
                        if not self.is_allowed_by_robots(dom, parsed.path):
                            continue
                    await self.queue.put(n)

            except Exception as e:
                logger.error(f"Error parsing {url}: {e}")

            self.queue.task_done()

    async def crawl(self):
        # enqueue seeds
        for s in self.seed_urls:
            n = self.normalize_url(s, '')
            if n:
                await self.queue.put(n)

        await self._ensure_session()
        tasks = []
        for _ in range(self.concurrency):
            tasks.append(asyncio.create_task(self.worker()))

        start = time.time()
        await self.queue.join()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start
        await self.session.close()
        logger.info(f"Crawl complete: pages indexed={len(self.index)}, duration={duration:.2f}s")
        return duration

    def save_sharded_index(self, folder='index'):
        if not os.path.exists(folder):
            os.makedirs(folder)
        shard_map = {chr(i): [] for i in range(97, 123)}
        shard_map['others'] = []

        for item in self.index:
            chars = set()
            title = item.get('title', '')
            if title:
                chars.add(title[0].lower())
            for kw in item.get('keywords', []):
                if kw:
                    chars.add(kw[0])
            for c in chars:
                target = c if c in shard_map else 'others'
                shard_map[target].append(item)

        for char, data in shard_map.items():
            if data:
                seen = set()
                unique = [x for x in data if not (x['url'] in seen or seen.add(x['url']))]
                with open(f"{folder}/{char}.json", 'w', encoding='utf-8') as f:
                    json.dump(unique, f, ensure_ascii=False)
        logger.info('Saved sharded index to %s', folder)


if __name__ == '__main__':
    import sys

    # Lightweight CLI for demonstration
    seeds = [
        'https://news.ycombinator.com/',
        'https://www.python.org/',
        'https://www.wikipedia.org/'
    ]
    if len(sys.argv) > 1:
        seeds = sys.argv[1:]

    crawler = AsyncFindrCrawler(seeds, max_pages=200, max_per_domain=10, concurrency=10)
    asyncio.run(crawler.crawl())
    crawler.save_sharded_index()
    print('Indexed', len(crawler.index), 'pages')
