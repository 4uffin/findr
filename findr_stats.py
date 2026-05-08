import json
import os
import time
from datetime import datetime
from pathlib import Path

class IndexStats:
    """
    Tracks comprehensive statistics about the findr indexing process.
    Maintains metrics like total pages indexed, crawl duration, domain breakdown, etc.
    """
    
    def __init__(self, stats_file="index_stats.json"):
        self.stats_file = stats_file
        self.stats = self._load_or_create_stats()
    
    def _load_or_create_stats(self):
        """Load existing stats or create a new stats file."""
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return self._create_fresh_stats()
        return self._create_fresh_stats()
    
    def _create_fresh_stats(self):
        """Create a fresh stats structure."""
        return {
            "metadata": {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            },
            "crawl_sessions": [],
            "total_pages_indexed": 0,
            "total_crawl_time_seconds": 0,
            "unique_domains": {},
            "success_rate": 0.0,
            "failed_urls": [],
            "largest_domains": [],
            "index_file_stats": {}
        }
    
    def start_session(self):
        """Start a new crawl session and return session ID."""
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session = {
            "id": session_id,
            "started_at": datetime.now().isoformat(),
            "pages_indexed": 0,
            "failed_count": 0,
            "domains_crawled": {},
            "duration_seconds": 0
        }
        self.stats["crawl_sessions"].append(session)
        return session_id
    
    def update_page_indexed(self, session_id, url, domain, success=True):
        """Record a page being indexed."""
        # Update session
        for session in self.stats["crawl_sessions"]:
            if session["id"] == session_id:
                if success:
                    session["pages_indexed"] += 1
                else:
                    session["failed_count"] += 1
                
                # Track domain breakdown
                if domain not in session["domains_crawled"]:
                    session["domains_crawled"][domain] = 0
                session["domains_crawled"][domain] += 1
                break
        
        # Update global stats
        if success:
            self.stats["total_pages_indexed"] += 1
        
        # Track unique domains
        if domain not in self.stats["unique_domains"]:
            self.stats["unique_domains"][domain] = 0
        self.stats["unique_domains"][domain] += 1
    
    def record_failed_url(self, url, error):
        """Record a failed URL."""
        self.stats["failed_urls"].append({
            "url": url,
            "error": str(error),
            "timestamp": datetime.now().isoformat()
        })
        # Keep only last 100 failures
        if len(self.stats["failed_urls"]) > 100:
            self.stats["failed_urls"] = self.stats["failed_urls"][-100:]
    
    def end_session(self, session_id, duration_seconds):
        """End a crawl session and calculate statistics."""
        for session in self.stats["crawl_sessions"]:
            if session["id"] == session_id:
                session["ended_at"] = datetime.now().isoformat()
                session["duration_seconds"] = duration_seconds
                
                # Calculate success rate for this session
                total_attempts = session["pages_indexed"] + session["failed_count"]
                if total_attempts > 0:
                    session["success_rate"] = (session["pages_indexed"] / total_attempts) * 100
                break
        
        self.stats["total_crawl_time_seconds"] += duration_seconds
        self._calculate_global_stats()
    
    def _calculate_global_stats(self):
        """Calculate aggregate statistics."""
        # Calculate success rate
        total_pages = self.stats["total_pages_indexed"]
        total_failures = sum(session.get("failed_count", 0) for session in self.stats["crawl_sessions"])
        total_attempts = total_pages + total_failures
        
        if total_attempts > 0:
            self.stats["success_rate"] = (total_pages / total_attempts) * 100
        
        # Get top domains
        sorted_domains = sorted(
            self.stats["unique_domains"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        self.stats["largest_domains"] = [
            {"domain": domain, "count": count} 
            for domain, count in sorted_domains[:20]
        ]
        
        self.stats["metadata"]["last_updated"] = datetime.now().isoformat()
    
    def analyze_index_files(self, index_folder="index"):
        """Analyze the generated index shards and record statistics."""
        if not os.path.exists(index_folder):
            return
        
        total_entries = 0
        shard_stats = {}
        
        for filename in os.listdir(index_folder):
            if filename.endswith('.json'):
                filepath = os.path.join(index_folder, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        count = len(data) if isinstance(data, list) else 1
                        shard_stats[filename] = {
                            "entries": count,
                            "file_size_bytes": os.path.getsize(filepath)
                        }
                        total_entries += count
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Error reading {filepath}: {e}")
        
        self.stats["index_file_stats"] = {
            "total_shards": len(shard_stats),
            "total_entries": total_entries,
            "shard_breakdown": shard_stats,
            "analyzed_at": datetime.now().isoformat()
        }
    
    def get_summary(self):
        """Return a human-readable summary of statistics."""
        return {
            "total_pages_indexed": self.stats["total_pages_indexed"],
            "unique_domains": len(self.stats["unique_domains"]),
            "total_crawl_time_hours": self.stats["total_crawl_time_seconds"] / 3600,
            "success_rate_percent": round(self.stats["success_rate"], 2),
            "failed_urls_count": len(self.stats["failed_urls"]),
            "total_crawl_sessions": len(self.stats["crawl_sessions"]),
            "top_10_domains": self.stats["largest_domains"][:10],
            "index_entries": self.stats["index_file_stats"].get("total_entries", 0),
            "index_shards": self.stats["index_file_stats"].get("total_shards", 0)
        }
    
    def print_report(self):
        """Print a formatted report of all statistics."""
        summary = self.get_summary()
        
        print("\n" + "="*60)
        print("FINDR INDEXING STATISTICS REPORT")
        print("="*60)
        print(f"\n📊 OVERALL STATISTICS")
        print(f"  • Total pages indexed: {summary['total_pages_indexed']:,}")
        print(f"  • Unique domains crawled: {summary['unique_domains']}")
        print(f"  • Total crawl time: {summary['total_crawl_time_hours']:.2f} hours")
        print(f"  • Success rate: {summary['success_rate_percent']}%")
        print(f"  • Failed URLs recorded: {summary['failed_urls_count']}")
        
        print(f"\n📈 CRAWL SESSIONS")
        print(f"  • Total sessions: {summary['total_crawl_sessions']}")
        if self.stats["crawl_sessions"]:
            latest_session = self.stats["crawl_sessions"][-1]
            print(f"  • Latest session: {latest_session['id']}")
            print(f"    - Pages indexed: {latest_session['pages_indexed']}")
            print(f"    - Failed: {latest_session['failed_count']}")
            print(f"    - Duration: {latest_session['duration_seconds']:.2f}s")
        
        print(f"\n🗂️  INDEX FILES")
        print(f"  • Total shards: {summary['index_shards']}")
        print(f"  • Total indexed entries: {summary['index_entries']:,}")
        
        print(f"\n🏆 TOP 10 DOMAINS")
        for i, domain_info in enumerate(summary['top_10_domains'], 1):
            print(f"  {i:2}. {domain_info['domain']:<40} ({domain_info['count']:4} pages)")
        
        print("\n" + "="*60 + "\n")
    
    def save(self):
        """Save statistics to disk."""
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)
    
    def export_csv(self, filename="findr_stats.csv"):
        """Export domain statistics to CSV."""
        import csv
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Domain', 'Pages Indexed', 'Percentage'])
            
            total = sum(self.stats["unique_domains"].values())
            for domain, count in sorted(
                self.stats["unique_domains"].items(),
                key=lambda x: x[1],
                reverse=True
            ):
                percentage = (count / total * 100) if total > 0 else 0
                writer.writerow([domain, count, f"{percentage:.2f}%"])


if __name__ == "__main__":
    # Example usage
    stats = IndexStats()
    
    # Simulate a crawl session
    session_id = stats.start_session()
    
    # Record some indexed pages
    stats.update_page_indexed(session_id, "https://example.com/page1", "example.com", True)
    stats.update_page_indexed(session_id, "https://example.com/page2", "example.com", True)
    stats.update_page_indexed(session_id, "https://github.com/page", "github.com", True)
    stats.update_page_indexed(session_id, "https://broken.com/page", "broken.com", False)
    
    # Record a failure
    stats.record_failed_url("https://broken.com/page", "Timeout error")
    
    # End the session
    stats.end_session(session_id, 120)
    
    # Analyze index files
    stats.analyze_index_files()
    
    # Print and save
    stats.print_report()
    stats.save()
    stats.export_csv()
    
    print("Stats saved to index_stats.json and findr_stats.csv")
