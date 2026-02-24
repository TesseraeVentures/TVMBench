#!/usr/bin/env python3
"""
Scrape rekt.news leaderboard and individual post-mortem pages.
Produces structured JSON for TVMBench corpus enrichment and Tesserae migration risk lookup.

Usage:
    python3 scrape_rekt.py                    # Scrape leaderboard only (fast)
    python3 scrape_rekt.py --full             # Scrape leaderboard + individual pages
    python3 scrape_rekt.py --full --limit 50  # Scrape first 50 entries with details
"""

import argparse
import json
import re
import time
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

OUTPUT_DIR = Path("/opt/tvmbench/data/rekt")

# TVM vulnerability category mapping for cross-chain exploit patterns
EVM_TO_TVM_MAPPING = {
    "reentrancy": {
        "tvm_equivalent": "bounce-handling",
        "explanation": "EVM reentrancy exploits asynchronous callback ordering. On TVM, the equivalent is bounce handler manipulation — messages that fail and return funds can corrupt state if bounce handlers are missing or incorrect.",
        "tvmbench_categories": ["TVB-001 – TVB-020"]
    },
    "flash_loan": {
        "tvm_equivalent": "message-chain-attacks",
        "explanation": "Flash loans exploit atomic composability. TVM has no atomic cross-contract calls — the equivalent is message chain ordering attacks where an attacker controls the sequence of async messages.",
        "tvmbench_categories": ["TVB-004 – TVB-025"]
    },
    "oracle_manipulation": {
        "tvm_equivalent": "cross-contract-interaction",
        "explanation": "Oracle manipulation on EVM uses synchronous reads. On TVM, oracle data arrives via messages — stale state between message hops is the equivalent attack surface.",
        "tvmbench_categories": ["TVB-056 – TVB-060"]
    },
    "access_control": {
        "tvm_equivalent": "authentication-access-control",
        "explanation": "EVM access control bugs (missing onlyOwner, etc.) map directly to TVM sender validation issues, with the added complexity of workchain-aware address validation.",
        "tvmbench_categories": ["TVB-036 – TVB-043"]
    },
    "bridge": {
        "tvm_equivalent": "cross-contract-interaction",
        "explanation": "Bridge exploits involve cross-chain message verification. On TVM, cross-shard and cross-workchain message routing add unique verification requirements.",
        "tvmbench_categories": ["TVB-056 – TVB-060"]
    },
    "upgrade": {
        "tvm_equivalent": "upgrade-migration-safety",
        "explanation": "Proxy upgrade bugs on EVM map to set_code attacks on TVM, where code replacement without proper state migration can corrupt contract storage.",
        "tvmbench_categories": ["TVB-013 – TVB-049"]
    },
    "integer_overflow": {
        "tvm_equivalent": "tvm-arithmetic",
        "explanation": "EVM integer overflow/underflow maps to TVM's 257-bit integer edge cases, negative number handling, and slice/builder overflow.",
        "tvmbench_categories": ["TVB-050 – TVB-055"]
    },
    "storage_collision": {
        "tvm_equivalent": "gas-storage-economics",
        "explanation": "EVM storage collision maps to TVM dictionary attacks, cell overflow, and storage rent exhaustion.",
        "tvmbench_categories": ["TVB-007 – TVB-030"]
    },
    "token_standard": {
        "tvm_equivalent": "standards-compliance",
        "explanation": "ERC-20/721 compliance gaps map to TEP-74/62/89 compliance issues on TVM.",
        "tvmbench_categories": ["TVB-010 – TVB-035"]
    }
}

# Keywords to classify attack vectors
ATTACK_KEYWORDS = {
    "reentrancy": ["reentrancy", "reentrant", "re-entrant", "recursive call"],
    "flash_loan": ["flash loan", "flashloan", "flash-loan", "atomic arbitrage"],
    "oracle_manipulation": ["oracle", "price manipulation", "price feed", "twap", "chainlink"],
    "access_control": ["access control", "permission", "privilege", "admin key", "owner", "governance attack"],
    "bridge": ["bridge", "cross-chain", "relay", "message verification"],
    "upgrade": ["upgrade", "proxy", "implementation", "delegatecall", "set_code"],
    "integer_overflow": ["overflow", "underflow", "integer", "arithmetic"],
    "storage_collision": ["storage collision", "storage slot", "proxy storage"],
    "token_standard": ["erc20", "erc721", "erc1155", "token standard", "approval", "transfer"],
}


def fetch_page(url: str, retries: int = 3) -> str:
    """Fetch a page with retries and rate limiting."""
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError) as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                print(f"  Failed to fetch {url}: {e}", file=sys.stderr)
                return ""


def parse_leaderboard(html: str) -> list[dict]:
    """Parse the rekt.news leaderboard page."""
    entries = []
    # Match patterns like: 1.$14,847,374,246 | 12/20/2020
    # The leaderboard has links to individual pages
    
    # Try to extract links and amounts
    # Pattern: <a href="/protocol-name/">...amount...|...date...</a>
    link_pattern = re.compile(r'href="(/[a-zA-Z0-9_-]+/)"[^>]*>.*?</a>', re.DOTALL)
    
    # Simpler: parse the text version we get from web_fetch
    lines = html.split("\n")
    for line in lines:
        # Match: - N.$AMOUNT | MM/DD/YYYY
        m = re.match(r'[-\s]*(\d+)\.\$([0-9,]+)\s*\|\s*(\d{1,2}/\d{1,2}/\d{2,4})', line.strip())
        if m:
            rank = int(m.group(1))
            amount_str = m.group(2).replace(",", "")
            date_str = m.group(3)
            try:
                amount = int(amount_str)
            except ValueError:
                amount = 0
            entries.append({
                "rank": rank,
                "amount_usd": amount,
                "date": date_str,
            })
    
    return entries


def scrape_leaderboard_html() -> str:
    """Scrape the rekt.news leaderboard page directly."""
    url = "https://rekt.news/leaderboard/"
    html = fetch_page(url)
    return html


def extract_protocol_links(html: str) -> list[dict]:
    """Extract protocol links from leaderboard HTML."""
    links = []
    # Look for links in the leaderboard entries
    pattern = re.compile(r'<a[^>]*href="(/[a-zA-Z0-9_-]+(?:-rekt)?/)"[^>]*>', re.IGNORECASE)
    for m in pattern.finditer(html):
        slug = m.group(1).strip("/")
        if slug not in ("leaderboard", "about", "paste", "search", "glossary"):
            links.append(slug)
    return links


def scrape_article(slug: str) -> dict:
    """Scrape an individual rekt.news article for post-mortem details."""
    url = f"https://rekt.news/{slug}/"
    html = fetch_page(url)
    if not html:
        return {}
    
    # Strip HTML tags for text analysis
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip().lower()
    
    # Extract title
    title_m = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    title = title_m.group(1).strip() if title_m else slug
    
    # Classify attack vector
    attack_vectors = []
    for vector, keywords in ATTACK_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                attack_vectors.append(vector)
                break
    
    # Detect chain
    chains = []
    chain_keywords = {
        "ethereum": ["ethereum", "eth ", "evm"],
        "bsc": ["binance smart chain", "bsc", "bnb chain"],
        "polygon": ["polygon", "matic"],
        "avalanche": ["avalanche", "avax"],
        "solana": ["solana", "sol "],
        "arbitrum": ["arbitrum"],
        "optimism": ["optimism"],
        "fantom": ["fantom"],
        "ton": ["ton ", "toncoin", "the open network"],
        "base": ["base chain", "base "],
    }
    for chain, kws in chain_keywords.items():
        for kw in kws:
            if kw.lower() in text:
                chains.append(chain)
                break
    
    # Map to TVM equivalents
    tvm_mappings = []
    for vector in set(attack_vectors):
        if vector in EVM_TO_TVM_MAPPING:
            tvm_mappings.append(EVM_TO_TVM_MAPPING[vector])
    
    return {
        "slug": slug,
        "title": title,
        "url": f"https://rekt.news/{slug}/",
        "attack_vectors": list(set(attack_vectors)),
        "chains": list(set(chains)),
        "tvm_equivalents": tvm_mappings,
        "text_length": len(text),
    }


def classify_entry(entry: dict) -> dict:
    """Add TVM mapping info to a leaderboard entry based on its article data."""
    if "article" in entry and entry["article"]:
        article = entry["article"]
        entry["attack_vectors"] = article.get("attack_vectors", [])
        entry["chains"] = article.get("chains", [])
        entry["tvm_equivalents"] = article.get("tvm_equivalents", [])
    return entry


def compute_stats(entries: list[dict]) -> dict:
    """Compute aggregate statistics for the rekt database."""
    total_lost = sum(e.get("amount_usd", 0) for e in entries)
    
    # Count by attack vector
    vector_counts = {}
    vector_totals = {}
    for e in entries:
        for v in e.get("attack_vectors", []):
            vector_counts[v] = vector_counts.get(v, 0) + 1
            vector_totals[v] = vector_totals.get(v, 0) + e.get("amount_usd", 0)
    
    # Count by chain
    chain_counts = {}
    for e in entries:
        for c in e.get("chains", []):
            chain_counts[c] = chain_counts.get(c, 0) + 1
    
    # Bridge/cross-chain specific losses
    bridge_losses = sum(
        e.get("amount_usd", 0) for e in entries
        if "bridge" in e.get("attack_vectors", [])
    )
    
    return {
        "total_entries": len(entries),
        "total_lost_usd": total_lost,
        "total_lost_formatted": f"${total_lost:,.0f}",
        "bridge_losses_usd": bridge_losses,
        "bridge_losses_formatted": f"${bridge_losses:,.0f}",
        "by_attack_vector": {
            k: {"count": vector_counts[k], "total_usd": vector_totals[k]}
            for k in sorted(vector_counts, key=lambda x: vector_totals.get(x, 0), reverse=True)
        },
        "by_chain": dict(sorted(chain_counts.items(), key=lambda x: x[1], reverse=True)),
        "entries_with_tvm_mapping": sum(1 for e in entries if e.get("tvm_equivalents")),
    }


def main():
    parser = argparse.ArgumentParser(description="Scrape rekt.news for TVMBench/Tesserae intelligence")
    parser.add_argument("--full", action="store_true", help="Scrape individual article pages too")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of articles to scrape (0=all)")
    args = parser.parse_args()
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Fetching rekt.news leaderboard...")
    html = scrape_leaderboard_html()
    
    if not html:
        print("Failed to fetch leaderboard. Trying cached data...", file=sys.stderr)
        cached = OUTPUT_DIR / "leaderboard.json"
        if cached.exists():
            entries = json.loads(cached.read_text())
            print(f"Loaded {len(entries)} cached entries.")
        else:
            print("No cached data available.", file=sys.stderr)
            sys.exit(1)
    else:
        # Parse leaderboard
        entries = parse_leaderboard(html)
        print(f"Found {len(entries)} leaderboard entries.")
        
        # Try to extract protocol slugs from the full HTML
        slugs = extract_protocol_links(html)
        print(f"Found {len(slugs)} protocol links.")
        
        # Match slugs to entries by position if possible
        for i, slug in enumerate(slugs):
            if i < len(entries):
                entries[i]["slug"] = slug
    
    if args.full:
        limit = args.limit if args.limit > 0 else len(entries)
        to_scrape = [e for e in entries[:limit] if e.get("slug")]
        print(f"\nScraping {len(to_scrape)} article pages...")
        
        for i, entry in enumerate(to_scrape):
            slug = entry["slug"]
            print(f"  [{i+1}/{len(to_scrape)}] {slug}...", end=" ", flush=True)
            article = scrape_article(slug)
            entry["article"] = article
            entry = classify_entry(entry)
            print(f"vectors={article.get('attack_vectors', [])} chains={article.get('chains', [])}")
            time.sleep(1)  # Rate limit
    
    # Save leaderboard
    leaderboard_path = OUTPUT_DIR / "leaderboard.json"
    leaderboard_path.write_text(json.dumps(entries, indent=2))
    print(f"\nSaved leaderboard to {leaderboard_path}")
    
    # Save EVM→TVM mapping reference
    mapping_path = OUTPUT_DIR / "evm_to_tvm_mapping.json"
    mapping_path.write_text(json.dumps(EVM_TO_TVM_MAPPING, indent=2))
    print(f"Saved EVM→TVM mapping to {mapping_path}")
    
    # Compute and save stats
    stats = compute_stats(entries)
    stats_path = OUTPUT_DIR / "stats.json"
    stats_path.write_text(json.dumps(stats, indent=2))
    print(f"Saved stats to {stats_path}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"REKT DATABASE SUMMARY")
    print(f"{'='*60}")
    print(f"Total entries:           {stats['total_entries']}")
    print(f"Total lost:              {stats['total_lost_formatted']}")
    print(f"Bridge/cross-chain:      {stats['bridge_losses_formatted']}")
    print(f"Entries with TVM mapping: {stats['entries_with_tvm_mapping']}")
    
    if stats.get("by_attack_vector"):
        print(f"\nBy attack vector:")
        for vec, data in stats["by_attack_vector"].items():
            print(f"  {vec:25s} {data['count']:3d} exploits  ${data['total_usd']:>15,.0f}")
    
    if stats.get("by_chain"):
        print(f"\nBy chain:")
        for chain, count in stats["by_chain"].items():
            print(f"  {chain:25s} {count:3d} exploits")


if __name__ == "__main__":
    main()
