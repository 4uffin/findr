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
    # Massive seed list with extreme diversity - 200+ URLs across tech, news, culture, science, and more
    seeds = [
        # === TECH & DEVELOPMENT (30+ seeds) ===
        "https://news.ycombinator.com/", "https://github.com/explore", "https://tldr.tech/",
        "https://www.producthunt.com/", "https://lobste.rs/", "https://slashdot.org/",
        "https://dev.to/", "https://css-tricks.com/", "https://www.infoq.com/",
        "https://techcrunch.com/", "https://www.theverge.com/", "https://arstechnica.com/",
        "https://wired.com/", "https://www.engadget.com/", "https://mashable.com/",
        "https://www.geekwire.com/", "https://venturebeat.com/", "https://9to5google.com/",
        "https://9to5mac.com/", "https://www.gsmarena.com/", "https://www.anandtech.com/",
        "https://www.tomshardware.com/", "https://www.linus.com/", "https://phoronix.com/",
        "https://www.bleepingcomputer.com/", "https://krebsonsecurity.com/", "https://www.schneier.com/",
        "https://securityweekly.com/", "https://www.zerodayinitiative.com/", "https://codeforces.com/",
        
        # === NEWS & CURRENT AFFAIRS (15+ seeds) ===
        "https://www.reuters.com/", "https://www.npr.org/", "https://www.theatlantic.com/",
        "https://www.bbc.com/", "https://www.cnn.com/", "https://www.theguardian.com/",
        "https://www.propublica.org/", "https://www.ft.com/", "https://www.economist.com/",
        "https://www.wsj.com/", "https://www.nytimes.com/", "https://www.washingtonpost.com/",
        "https://apnews.com/", "https://www.politico.com/", "https://www.vice.com/",
        
        # === REFERENCE & KNOWLEDGE (12+ seeds) ===
        "https://en.wikipedia.org/wiki/Portal:Contents", "https://archive.org/details/texts",
        "https://www.wiktionary.org/", "https://www.britannica.com/", "https://stackoverflow.com/",
        "https://stackexchange.com/", "https://www.gutenberg.org/", "https://www.semanticscholar.org/",
        "https://scholar.google.com/", "https://www.libgen.is/", "https://standardebooks.org/",
        "https://www.forvo.com/",
        
        # === WEB CULTURE & COMMUNITIES (18+ seeds) ===
        "https://neocities.org/browse", "https://wiby.me/", "https://68k.news/",
        "https://kottke.org/", "https://www.metafilter.com/", "https://boingboing.net/",
        "https://www.reddit.com/", "https://news.ycombinator.com/best", "https://medium.com/",
        "https://www.quora.com/", "https://www.producthunt.com/", "https://tildes.net/",
        "https://lobsters.info/", "https://news.ycombinator.com/newest", "https://news.ycombinator.com/ask",
        "https://pinboard.in/", "https://del.icio.us/", "https://digg.com/",
        
        # === SCIENCE, NATURE & RESEARCH (15+ seeds) ===
        "https://www.nature.com/", "https://www.science.org/", "https://www.sciencedaily.com/",
        "https://phys.org/", "https://www.nasa.gov/", "https://www.esa.int/",
        "https://arxiv.org/", "https://www.plos.org/", "https://elifesciences.org/",
        "https://www.frontiersin.org/", "https://www.ncbi.nlm.nih.gov/pubmed/", "https://www.pubmed.gov/",
        "https://www.biorxiv.org/", "https://www.medrxiv.org/", "https://www.chemrxiv.org/",
        
        # === LEARNING & EDUCATION (12+ seeds) ===
        "https://www.freecodecamp.org/", "https://www.udemy.com/", "https://www.coursera.org/",
        "https://www.edx.org/", "https://www.codecademy.com/", "https://www.khanacademy.org/",
        "https://www.duolingo.com/", "https://www.skillshare.com/", "https://www.pluralsight.com/",
        "https://www.udacity.com/", "https://www.masterclass.com/", "https://www.brilliant.org/",
        
        # === ARTS, DESIGN & CULTURE (15+ seeds) ===
        "https://artsy.net/", "https://www.behance.net/", "https://dribbble.com/",
        "https://www.designobserver.com/", "https://www.dezeen.com/", "https://www.wallpaper.com/",
        "https://www.smithsonianmag.com/", "https://www.louvre.fr/", "https://www.moma.org/",
        "https://www.guggenheim.org/", "https://www.themet.org/", "https://www.uffizi.org/",
        "https://www.theonion.com/", "https://www.clickhole.com/",
        
        # === ENTERTAINMENT & MEDIA (15+ seeds) ===
        "https://www.imdb.com/", "https://www.youtube.com/", "https://www.twitch.tv/",
        "https://www.netflix.com/", "https://www.hulu.com/", "https://www.disneyplus.com/",
        "https://www.primevideo.com/", "https://www.spotify.com/", "https://www.apple.com/music/",
        "https://www.xkcd.com/", "https://www.gocomics.com/", "https://www.penny-arcade.com/",
        "https://www.smashingmagazine.com/", "https://www.collider.com/", "https://www.polygon.com/",
        
        # === BUSINESS & INNOVATION (12+ seeds) ===
        "https://www.fastcompany.com/", "https://www.forbes.com/", "https://www.crunchbase.com/",
        "https://www.businessinsider.com/", "https://www.entrepreneur.com/", "https://www.inc.com/",
        "https://www.mckinsey.com/", "https://www.bcg.com/", "https://www.bain.com/",
        "https://www.linkedin.com/", "https://www.angellist.com/", "https://a16z.com/",
        
        # === INDIE WEB & NICHE COMMUNITIES (15+ seeds) ===
        "https://indieweb.org/", "https://gemini.circumlunar.space/", "https://tilde.club/",
        "https://daily.dev/", "https://www.lesswrong.com/", "https://effective-altruism.org/",
        "https://www.rationality.org/", "https://en.wikiversity.org/", "https://www.freenode.net/",
        "https://www.libera.chat/", "https://matrix.org/", "https://www.discord.com/",
        "https://www.slack.com/", "https://www.telegram.org/", "https://www.signal.org/",
        
        # === PROGRAMMING LANGUAGES & FRAMEWORKS (12+ seeds) ===
        "https://www.rust-lang.org/", "https://golang.org/", "https://www.python.org/",
        "https://www.typescriptlang.org/", "https://www.ruby-lang.org/", "https://www.php.net/",
        "https://www.java.com/", "https://kotlinlang.org/", "https://www.scala-lang.org/",
        "https://www.haskell.org/", "https://clojure.org/", "https://elixir-lang.org/",
        
        # === DATABASES, TOOLS & INFRASTRUCTURE (12+ seeds) ===
        "https://www.postgresql.org/", "https://www.mongodb.com/", "https://redis.io/",
        "https://www.mysql.com/", "https://www.oracle.com/database/", "https://www.elastic.co/",
        "https://www.docker.com/", "https://kubernetes.io/", "https://www.terraform.io/",
        "https://www.ansible.com/", "https://www.jenkins.io/", "https://www.githubstatus.com/",
        
        # === OPEN SOURCE & COMMUNITY (12+ seeds) ===
        "https://www.linux.org/", "https://www.apache.org/", "https://www.mozilla.org/",
        "https://www.fsf.org/", "https://www.gnu.org/", "https://www.linuxfoundation.org/",
        "https://www.cncf.io/", "https://www.eclipse.org/", "https://www.apache.org/",
        "https://www.canonical.com/", "https://www.redhat.com/", "https://www.ubuntu.com/",
        
        # === FINANCE & CRYPTO (10+ seeds) ===
        "https://www.coindesk.com/", "https://www.cointelegraph.com/", "https://decrypt.co/",
        "https://www.bloomberg.com/", "https://www.cnbc.com/", "https://www.marketwatch.com/",
        "https://www.investopedia.com/", "https://www.stonks.com/", "https://finance.yahoo.com/",
        "https://www.trading212.com/",
        
        # === GAMING & ESPORTS (10+ seeds) ===
        "https://www.gamespot.com/", "https://www.ign.com/", "https://www.pcgamer.com/",
        "https://www.rockpapershotgun.com/", "https://www.escapist.com/", "https://kotaku.com/",
        "https://www.twitch.tv/directory/", "https://www.esports.com/", "https://dotesports.com/",
        "https://www.espn.com/esports/",
        
        # === HEALTH & WELLNESS (8+ seeds) ===
        "https://www.healthline.com/", "https://www.webmd.com/", "https://www.mayoclinic.org/",
        "https://www.cdc.gov/", "https://www.who.int/", "https://www.nih.gov/",
        "https://pubmed.ncbi.nlm.nih.gov/", "https://www.fitbit.com/",
        
        # === TRAVEL & GEOGRAPHY (8+ seeds) ===
        "https://www.tripadvisor.com/", "https://www.booking.com/", "https://www.airbnb.com/",
        "https://www.lonely planet.com/", "https://www.nationalgeographic.com/travel/",
        "https://www.wikivoyage.org/", "https://www.google.com/maps/", "https://www.openstreetmap.org/",
        
        # === FOOD & COOKING (8+ seeds) ===
        "https://www.allrecipes.com/", "https://www.food52.com/", "https://www.bonappetit.com/",
        "https://www.gourmet.com/", "https://www.seriouseats.com/", "https://www.ramsayinhell.com/",
        "https://www.gordonramsay.com/", "https://michelin-guide.com/",
        
        # === PHILOSOPHY & ETHICS (8+ seeds) ===
        "https://plato.stanford.edu/", "https://www.iep.utm.edu/", "https://www.britannica.com/topic/philosophy",
        "https://www.philosophybasics.com/", "https://www.philosophypages.com/", "https://www.opensocietyfoundations.org/",
        "https://www.effectivealtruism.org/", "https://www.givingwhatwecan.org/",
        
        # === HISTORY & ARCHIVES (8+ seeds) ===
        "https://www.history.com/", "https://www.bbc.com/history/", "https://www.britannica.com/history/",
        "https://www.facinghistory.org/", "https://www.ushmm.org/", "https://www.iwm.org.uk/",
        "https://www.archives.gov/", "https://www.loc.gov/",
        
        # === ENVIRONMENTAL & SUSTAINABILITY (8+ seeds) ===
        "https://www.ecologytoday.net/", "https://www.nationalgeographic.com/environment/",
        "https://www.renewableenergyworld.com/", "https://www.carbontrust.com/", "https://www.wri.org/",
        "https://www.greenpeace.org/", "https://www.worldwildlife.org/", "https://www.nature.org/",
        
        # === SOCIAL JUSTICE & ACTIVISM (8+ seeds) ===
        "https://www.amnesty.org/", "https://www.hrw.org/", "https://www.aclu.org/",
        "https://www.splcenter.org/", "https://www.humanrights.org/", "https://www.undp.org/",
        "https://www.unicef.org/", "https://www.oxfam.org/",
        
        # === RANDOM INTERESTING (10+ seeds) ===
        "https://www.reddit.com/r/InternetIsBeautiful/", "https://www.askamanager.org/",
        "https://waitbutwhy.com/", "https://www.cracked.com/", "https://www.collegehumor.com/",
        "https://www.hackaday.com/", "https://www.make-digital.com/", "https://www.instructables.com/",
        "https://www.thingiverse.com/", "https://www.adafruit.com/",
    ]
    spider = FindrSpider(seeds)
    spider.crawl()
    spider.save_sharded_index()
