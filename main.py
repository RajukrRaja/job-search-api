# main.py - Advanced Job Scraper - Individual Jobs Only
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
import random
import hashlib
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re
import asyncio
import aiohttp

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="50+ Platform Job Scraper - Individual Jobs", description="RapidAPI + Google Jobs + Remote APIs - Real Jobs Only", version="21.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RESULTS_DIR = Path("scraped_data")
RESULTS_DIR.mkdir(exist_ok=True)

class JobSearchRequest(BaseModel):
    keyword: str
    location: str = "India"
    max_results: int = 500

class JobResponse(BaseModel):
    id: str
    platform: str
    title: str
    company: str
    location: str
    url: str
    date: str
    salary: Optional[str] = None
    description: Optional[str] = None
    source_api: str
    relevance_score: Optional[float] = None
    is_individual_job: bool = True

class AdvancedJobScraper:
    """Advanced scraper - ONLY INDIVIDUAL JOB LISTINGS"""
    
    def __init__(self):
        self.session = requests.Session()
        
        # SerpAPI Key
        self.serpapi_key = "1ade4715779f776b10c8d6b65e3e5113a2daedf3f4c9422e6bcc59cdf76ebd70"
        
        # RapidAPI Key
        self.rapidapi_key = "666f55b385msh866a540b0521ca7p1394ddjsncf5d0a5f7b5c"
        self.rapidapi_headers = {
            'x-rapidapi-key': self.rapidapi_key,
            'x-rapidapi-host': 'jsearch.p.rapidapi.com',
            'Content-Type': 'application/json'
        }
        
        # User agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
        
        # Keywords that indicate it's a job board page, NOT an individual job
        self.job_board_indicators = [
            'apply to', 'jobs-', 'jobs in', 'vacancies', 'openings', 'find jobs',
            'search jobs', 'browse jobs', 'careers', 'opportunities', 'hiring now',
            'job site', 'job portal', 'job search', 'thousands of', 'hundreds of',
            'explore jobs', 'discover jobs', 'view all', 'see all', 'all jobs'
        ]
    
    def is_individual_job(self, title, description, company):
        """Check if this is an individual job listing or a job board page"""
        text_to_check = f"{title} {description} {company}".lower()
        
        # Check for job board indicators
        for indicator in self.job_board_indicators:
            if indicator in text_to_check:
                return False
        
        # Check if title contains numbers (like "110000 jobs")
        if re.search(r'\d+\s*(jobs|openings|vacancies|positions)', title.lower()):
            return False
        
        # Check if it's too generic
        generic_titles = ['software developer jobs', 'developer jobs', 'it jobs', 'tech jobs']
        if title.lower() in generic_titles:
            return False
        
        # Must have a specific company name
        if company.lower() in ['not specified', 'unknown', 'job board', 'job portal', '']:
            return False
        
        return True
    
    # ==================== 1. RAPIDAPI JSEARCH - INDIVIDUAL JOBS ====================
    
    def search_rapidapi_individual_jobs(self, keyword, location, max_pages=15):
        """RapidAPI JSearch - Extract ONLY individual job listings"""
        all_jobs = []
        platforms_found = set()
        
        logger.info(f"🚀 RapidAPI - Fetching INDIVIDUAL jobs only...")
        
        for page in range(1, max_pages + 1):
            try:
                url = "https://jsearch.p.rapidapi.com/search"
                
                params = {
                    'query': f"{keyword} in {location}",
                    'page': page,
                    'num_pages': 1,
                    'date_posted': 'month',
                    'remote_jobs_only': 'false'
                }
                
                response = self.session.get(url, headers=self.rapidapi_headers, params=params, timeout=25)
                
                if response.status_code == 200:
                    data = response.json()
                    page_jobs = 0
                    
                    for job in data.get('data', []):
                        # Extract job details
                        title = job.get('job_title', 'Not specified')
                        description = job.get('job_description', '')
                        company = job.get('employer_name', 'Not specified')
                        
                        # Check if it's an individual job
                        if not self.is_individual_job(title, description, company):
                            continue
                        
                        # Detect platform from URL
                        url_lower = job.get('job_apply_link', '').lower()
                        
                        platform = "Job Board"
                        if 'indeed' in url_lower:
                            platform = "Indeed"
                        elif 'linkedin' in url_lower:
                            platform = "LinkedIn"
                        elif 'glassdoor' in url_lower:
                            platform = "Glassdoor"
                        elif 'naukri' in url_lower:
                            platform = "Naukri.com"
                        elif 'monster' in url_lower:
                            platform = "Monster"
                        elif 'wellfound' in url_lower:
                            platform = "Wellfound"
                        elif 'remote' in url_lower:
                            platform = "Remote Job Board"
                        
                        platforms_found.add(platform)
                        
                        # Extract salary
                        salary = "Not specified"
                        if job.get('job_min_salary') or job.get('job_max_salary'):
                            min_sal = job.get('job_min_salary', '')
                            max_sal = job.get('job_max_salary', '')
                            currency = job.get('job_salary_currency', '₹')
                            if min_sal and max_sal:
                                salary = f"{currency}{min_sal} - {currency}{max_sal}"
                            elif min_sal:
                                salary = f"From {currency}{min_sal}"
                        
                        # Clean description
                        clean_desc = description[:400].replace('\n', ' ').strip()
                        if len(clean_desc) > 400:
                            clean_desc = clean_desc[:397] + "..."
                        
                        all_jobs.append({
                            'platform': platform,
                            'title': title,
                            'company': company,
                            'location': job.get('job_city', job.get('job_state', location)),
                            'url': job.get('job_apply_link', 'N/A'),
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'salary': salary,
                            'description': clean_desc,
                            'source_api': 'RapidAPI JSearch',
                            'posted_time': job.get('job_posted_at_datetime_utc', 'Recently'),
                            'is_individual_job': True
                        })
                        page_jobs += 1
                    
                    logger.info(f"  ✅ RapidAPI Page {page}: {page_jobs} individual jobs")
                    
                    # Stop if no more jobs
                    if len(data.get('data', [])) < 5:
                        break
                        
                else:
                    logger.warning(f"  ⚠️ RapidAPI page {page} failed: {response.status_code}")
                    
                time.sleep(0.3)  # Rate limiting
                
            except Exception as e:
                logger.error(f"  ❌ RapidAPI page {page} error: {e}")
        
        logger.info(f"📊 RapidAPI Summary: {len(all_jobs)} individual jobs from {len(platforms_found)} platforms")
        return all_jobs
    
    # ==================== 2. GOOGLE JOBS - INDIVIDUAL JOBS ====================
    
    def search_google_jobs_individual(self, keyword, location, max_pages=20):
        """Google Jobs via SerpAPI - ONLY individual job listings"""
        all_jobs = []
        
        logger.info(f"🚀 Google Jobs - Fetching INDIVIDUAL jobs...")
        
        for page in range(max_pages):
            try:
                url = "https://serpapi.com/search.json"
                
                params = {
                    'api_key': self.serpapi_key,
                    'engine': 'google_jobs',
                    'q': f"{keyword} {location}",
                    'hl': 'en',
                    'gl': 'in' if 'india' in location.lower() else 'us',
                    'start': page * 10,
                    'num': 10
                }
                
                response = self.session.get(url, params=params, timeout=20)
                
                if response.status_code == 200:
                    data = response.json()
                    jobs_data = data.get('jobs_results', [])
                    
                    if not jobs_data:
                        break
                    
                    page_jobs = 0
                    for job in jobs_data:
                        title = job.get('title', 'Not specified')
                        company = job.get('company_name', 'Not specified')
                        
                        # Skip job board landing pages
                        if not self.is_individual_job(title, '', company):
                            continue
                        
                        salary = "Not specified"
                        if job.get('detected_extensions', {}).get('salary'):
                            salary = job['detected_extensions']['salary']
                        elif job.get('salary'):
                            salary = job['salary']
                        
                        description = job.get('description', '')
                        if not description and job.get('job_highlights'):
                            highlights = job.get('job_highlights', [])
                            if highlights:
                                description = ' '.join(highlights[:3])
                        
                        # Clean description
                        clean_desc = description[:400].replace('\n', ' ').strip()
                        if len(clean_desc) > 400:
                            clean_desc = clean_desc[:397] + "..."
                        
                        all_jobs.append({
                            'platform': 'Google Jobs',
                            'title': title,
                            'company': company,
                            'location': job.get('location', location),
                            'url': job.get('share_link', job.get('share_url', 'N/A')),
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'salary': salary,
                            'description': clean_desc,
                            'source_api': 'SerpAPI Google Jobs',
                            'posted_time': job.get('detected_extensions', {}).get('posted_at', 'Recently'),
                            'is_individual_job': True
                        })
                        page_jobs += 1
                    
                    logger.info(f"  ✅ Google Jobs Page {page + 1}: {page_jobs} individual jobs")
                    
                else:
                    logger.warning(f"  ⚠️ Google Jobs page {page + 1} failed")
                    
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"  ❌ Google Jobs page {page + 1} error: {e}")
        
        logger.info(f"📊 Google Jobs Summary: {len(all_jobs)} individual jobs")
        return all_jobs
    
    # ==================== 3. REMOTE JOB APIS - INDIVIDUAL JOBS ====================
    
    def search_remote_apis_individual(self, keyword):
        """Fetch INDIVIDUAL jobs from remote job APIs"""
        all_jobs = []
        
        logger.info(f"🚀 Remote APIs - Fetching INDIVIDUAL remote jobs...")
        
        # Remotive API - Best for individual remote jobs
        try:
            response = self.session.get(f"https://remotive.com/api/remote-jobs?search={keyword}", timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                jobs_found = 0
                
                for job in data.get('jobs', []):
                    title = job.get('title', '')
                    
                    if keyword.lower() in title.lower():
                        company = job.get('company_name', 'Not specified')
                        
                        if self.is_individual_job(title, job.get('description', ''), company):
                            all_jobs.append({
                                'platform': 'Remotive',
                                'title': title,
                                'company': company,
                                'location': job.get('candidate_required_location', 'Remote'),
                                'url': job.get('url', 'N/A'),
                                'date': job.get('publication_date', datetime.now().strftime('%Y-%m-%d'))[:10],
                                'salary': job.get('salary', 'Not specified'),
                                'description': job.get('description', '')[:400],
                                'source_api': 'Remotive API',
                                'is_individual_job': True
                            })
                            jobs_found += 1
                
                logger.info(f"  ✅ Remotive: {jobs_found} individual jobs")
                
        except Exception as e:
            logger.error(f"  ❌ Remotive error: {e}")
        
        # Arbeitnow API
        try:
            response = self.session.get("https://www.arbeitnow.com/api/job-board-api", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                jobs_found = 0
                
                for job in data.get('data', []):
                    title = job.get('title', '')
                    
                    if keyword.lower() in title.lower():
                        company = job.get('company_name', 'Not specified')
                        
                        if self.is_individual_job(title, job.get('description', ''), company):
                            all_jobs.append({
                                'platform': 'Arbeitnow',
                                'title': title,
                                'company': company,
                                'location': job.get('location', 'Europe'),
                                'url': job.get('url', 'N/A'),
                                'date': job.get('created_at', datetime.now().strftime('%Y-%m-%d'))[:10],
                                'description': job.get('description', '')[:400],
                                'source_api': 'Arbeitnow API',
                                'is_individual_job': True
                            })
                            jobs_found += 1
                
                logger.info(f"  ✅ Arbeitnow: {jobs_found} individual jobs")
                
        except Exception as e:
            logger.error(f"  ❌ Arbeitnow error: {e}")
        
        return all_jobs
    
    # ==================== MASTER METHOD ====================
    
    def scrape_all_individual_jobs(self, keyword, location):
        """Master method - Fetch ONLY individual job listings from all sources"""
        all_jobs = []
        
        print(f"\n{'='*100}")
        print(f"🎯 INDIVIDUAL JOB SCRAPER - NO LANDING PAGES")
        print(f"📝 Keyword: {keyword}")
        print(f"📍 Location: {location}")
        print(f"{'='*100}\n")
        
        # ============ PARALLEL FETCHING ============
        print("🚀 FETCHING INDIVIDUAL JOBS FROM ALL SOURCES...")
        print("-" * 60)
        
        results = {}
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(self.search_rapidapi_individual_jobs, keyword, location, 12): "RapidAPI (50+ Platforms)",
                executor.submit(self.search_google_jobs_individual, keyword, location, 15): "Google Jobs",
                executor.submit(self.search_remote_apis_individual, keyword): "Remote APIs",
            }
            
            for future in as_completed(futures):
                source = futures[future]
                try:
                    jobs = future.result(timeout=120)
                    results[source] = jobs
                    
                    # Filter individual jobs only
                    individual_jobs = [j for j in jobs if j.get('is_individual_job', True)]
                    all_jobs.extend(individual_jobs)
                    
                    print(f"\n✅ {source}: {len(individual_jobs)} individual jobs")
                    
                except Exception as e:
                    print(f"\n❌ {source} failed: {e}")
                    results[source] = []
        
        # ============ DEDUPLICATION ============
        print(f"\n{'='*100}")
        print("🔄 DEDUPLICATING JOBS...")
        print("-" * 60)
        
        unique_jobs = []
        seen = set()
        platform_stats = {}
        company_stats = {}
        
        for job in all_jobs:
            # Create unique key
            title_key = re.sub(r'[^\w\s]', '', job['title'].lower())[:60]
            company_key = re.sub(r'[^\w\s]', '', job['company'].lower())[:40]
            key = f"{title_key}_{company_key}"
            
            if key not in seen:
                seen.add(key)
                
                # Generate ID
                job['id'] = hashlib.md5(f"{job['title']}_{job['company']}_{job['date']}".encode()).hexdigest()[:8]
                
                # Calculate relevance score
                relevance = 0.5  # Base score
                if keyword.lower() in job['title'].lower():
                    relevance += 0.3
                if job.get('description') and keyword.lower() in job['description'].lower():
                    relevance += 0.2
                if job.get('salary') and job['salary'] != 'Not specified':
                    relevance += 0.2
                job['relevance_score'] = round(relevance, 2)
                
                # Track stats
                platform = job['platform']
                platform_stats[platform] = platform_stats.get(platform, 0) + 1
                
                company = job['company']
                company_stats[company] = company_stats.get(company, 0) + 1
                
                unique_jobs.append(job)
        
        # Sort by relevance
        unique_jobs.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        # ============ FINAL SUMMARY ============
        print(f"\n{'='*100}")
        print(f"📊 FINAL RESULTS - INDIVIDUAL JOBS ONLY")
        print(f"{'='*100}")
        print(f"  • Total jobs fetched (before filtering): {len(all_jobs)}")
        print(f"  • Unique individual jobs: {len(unique_jobs)}")
        print(f"  • Platforms: {len(platform_stats)}")
        
        print(f"\n🏢 TOP 10 PLATFORMS:")
        for platform, count in sorted(platform_stats.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  • {platform}: {count} jobs")
        
        print(f"\n💼 TOP 15 COMPANIES HIRING:")
        for company, count in sorted(company_stats.items(), key=lambda x: x[1], reverse=True)[:15]:
            if company != 'Not specified':
                print(f"  • {company}: {count} openings")
        
        # Sample individual jobs
        print(f"\n📋 SAMPLE INDIVIDUAL JOBS:")
        for job in unique_jobs[:10]:
            print(f"  • {job['title'][:50]} at {job['company'][:30]} - {job['platform']}")
        
        print(f"{'='*100}\n")
        
        return unique_jobs

# Initialize scraper
scraper = AdvancedJobScraper()

@app.get("/", response_class=HTMLResponse)
async def root():
    """Enhanced web interface - Individual Jobs Only"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Individual Job Scraper - Real Jobs Only</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px;
                text-align: center;
            }
            .header h1 { font-size: 2.5em; margin-bottom: 10px; }
            .header p { font-size: 1.1em; opacity: 0.9; }
            .warning-banner {
                background: #ffc107;
                color: #333;
                padding: 10px;
                text-align: center;
                font-weight: bold;
            }
            .api-grid {
                display: flex;
                justify-content: center;
                gap: 10px;
                margin-top: 20px;
                flex-wrap: wrap;
            }
            .api-tag {
                background: rgba(255,255,255,0.2);
                padding: 5px 12px;
                border-radius: 20px;
                font-size: 0.8em;
            }
            .search-box {
                padding: 40px;
                background: #f8f9fa;
            }
            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr auto;
                gap: 20px;
                align-items: end;
            }
            input {
                width: 100%;
                padding: 12px;
                border: 2px solid #ddd;
                border-radius: 8px;
                font-size: 16px;
            }
            button {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 12px 30px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                cursor: pointer;
                font-weight: bold;
            }
            button:hover { transform: translateY(-2px); }
            .loading {
                text-align: center;
                padding: 60px;
                display: none;
            }
            .loading.active { display: block; }
            .spinner {
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .results { padding: 40px; display: none; }
            .results.active { display: block; }
            .stats {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: #f8f9fa;
                padding: 20px;
                text-align: center;
                border-radius: 12px;
            }
            .stat-number { font-size: 2em; font-weight: bold; color: #667eea; }
            .job-card {
                background: white;
                border: 2px solid #e0e0e0;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 20px;
                cursor: pointer;
                transition: all 0.3s;
            }
            .job-card:hover {
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                transform: translateY(-2px);
                border-color: #667eea;
            }
            .job-title { font-size: 1.2em; font-weight: bold; margin-bottom: 8px; color: #333; }
            .job-company { color: #667eea; margin-bottom: 10px; font-weight: 500; }
            .job-meta { display: flex; gap: 15px; color: #666; font-size: 0.9em; flex-wrap: wrap; }
            .salary { color: #28a745; font-weight: bold; }
            .api-badge {
                background: #e9ecef;
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.75em;
            }
            .individual-badge {
                background: #28a745;
                color: white;
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.7em;
                margin-left: 5px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Individual Job Scraper Pro</h1>
                <p>Only Real Job Listings - No Landing Pages or Aggregators</p>
                <div class="api-grid">
                    <span class="api-tag">📡 RapidAPI (50+ Platforms)</span>
                    <span class="api-tag">🔍 Google Jobs</span>
                    <span class="api-tag">🌍 Remote APIs</span>
                    <span class="api-tag">💼 Individual Jobs Only</span>
                </div>
            </div>
            
            <div class="warning-banner">
                ⚡ ONLY INDIVIDUAL JOB LISTINGS - NO "1000+ Jobs" landing pages
            </div>
            
            <div class="search-box">
                <div class="form-row">
                    <div class="form-group">
                        <label>🔍 Job Title</label>
                        <input type="text" id="keyword" placeholder="Software Developer, Data Scientist" value="Software Developer">
                    </div>
                    <div class="form-group">
                        <label>📍 Location</label>
                        <input type="text" id="location" placeholder="India, USA, Remote" value="India">
                    </div>
                    <div>
                        <button onclick="searchJobs()">🔎 Find Individual Jobs</button>
                    </div>
                </div>
            </div>
            
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <h3>Fetching INDIVIDUAL job listings...</h3>
                <p>Filtering out job board pages and aggregators</p>
                <p style="margin-top: 10px; font-size: 0.9em; color: #666;">This ensures you only see real, specific job openings</p>
            </div>
            
            <div class="results" id="results">
                <div class="stats" id="stats"></div>
                <div id="jobList"></div>
            </div>
        </div>
        
        <script>
            let currentResults = [];
            
            async function searchJobs() {
                const keyword = document.getElementById('keyword').value;
                const location = document.getElementById('location').value;
                
                document.getElementById('loading').classList.add('active');
                document.getElementById('results').classList.remove('active');
                
                try {
                    const response = await fetch('/api/search', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ keyword, location, max_results: 500 })
                    });
                    
                    const data = await response.json();
                    currentResults = data;
                    displayResults(data);
                } catch (error) {
                    alert('Error: ' + error.message);
                } finally {
                    document.getElementById('loading').classList.remove('active');
                }
            }
            
            function displayResults(data) {
                if (!data || data.length === 0) {
                    document.getElementById('jobList').innerHTML = '<p style="text-align:center;padding:40px;">No individual jobs found. Try different keywords!</p>';
                    document.getElementById('results').classList.add('active');
                    return;
                }
                
                // Count platforms
                const platformCount = {};
                data.forEach(job => {
                    platformCount[job.platform] = (platformCount[job.platform] || 0) + 1;
                });
                
                document.getElementById('stats').innerHTML = `
                    <div class="stat-card"><div class="stat-number">${data.length}</div><div>Individual Jobs</div></div>
                    <div class="stat-card"><div class="stat-number">${Object.keys(platformCount).length}</div><div>Platforms</div></div>
                    <div class="stat-card"><div class="stat-number">✓</div><div>Real Listings Only</div></div>
                `;
                
                document.getElementById('jobList').innerHTML = data.map(job => `
                    <div class="job-card" onclick="window.open('${job.url}', '_blank')">
                        <div class="job-title">
                            ${escapeHtml(job.title)}
                            <span class="individual-badge">✓ Individual Job</span>
                        </div>
                        <div class="job-company">🏢 ${escapeHtml(job.company)}</div>
                        <div class="job-meta">
                            <span>📍 ${escapeHtml(job.location)}</span>
                            ${job.salary && job.salary !== 'Not specified' ? `<span class="salary">💰 ${escapeHtml(job.salary)}</span>` : ''}
                            <span class="api-badge">📡 ${escapeHtml(job.platform)}</span>
                            ${job.relevance_score ? `<span>⭐ ${job.relevance_score}</span>` : ''}
                        </div>
                        ${job.description ? `<div style="margin-top: 10px; font-size: 0.85em; color: #666;">${escapeHtml(job.description.substring(0, 200))}...</div>` : ''}
                    </div>
                `).join('');
                
                document.getElementById('results').classList.add('active');
            }
            
            function escapeHtml(text) {
                if (!text) return '';
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
        </script>
    </body>
    </html>
    """

@app.post("/api/search")
async def search_jobs(request: JobSearchRequest):
    """Search for INDIVIDUAL jobs only"""
    try:
        logger.info(f"🔍 Starting individual job search: {request.keyword} in {request.location}")
        
        jobs = scraper.scrape_all_individual_jobs(
            keyword=request.keyword,
            location=request.location
        )
        
        # Limit results
        jobs = jobs[:request.max_results]
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = RESULTS_DIR / f"individual_jobs_{request.keyword}_{timestamp}.json"
        
        df = pd.DataFrame(jobs)
        csv_file = RESULTS_DIR / f"individual_jobs_{request.keyword}_{timestamp}.csv"
        df.to_csv(csv_file, index=False)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Individual job search complete: {len(jobs)} jobs found")
        
        return jobs
    
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "mode": "INDIVIDUAL_JOBS_ONLY",
        "apis_configured": [
            "RapidAPI JSearch (50+ platforms) - Individual Jobs Only",
            "SerpAPI Google Jobs - Individual Jobs Only",
            "Remotive API - Individual Remote Jobs",
            "Arbeitnow API - Individual European Jobs"
        ],
        "filtering": {
            "job_board_pages_filtered": True,
            "aggregator_pages_filtered": True,
            "only_individual_listings": True
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("="*100)
    print("🎯 INDIVIDUAL JOB SCRAPER - REAL JOBS ONLY")
    print("="*100)
    print("📡 APIs ACTIVE (Individual Jobs Only):")
    print("  • RapidAPI JSearch - Individual jobs from 50+ platforms")
    print("  • SerpAPI Google Jobs - Individual Google Jobs listings")
    print("  • Remotive API - Individual remote jobs")
    print("  • Arbeitnow API - Individual European jobs")
    print("\n🚫 AUTOMATICALLY FILTERED OUT:")
    print("  • Job board landing pages (e.g., '1000+ Software Developer Jobs')")
    print("  • Job aggregator pages")
    print("  • Generic job search result pages")
    print("  • Company career pages without specific jobs")
    print("\n✅ ONLY SHOWING:")
    print("  • Individual job listings with specific titles")
    print("  • Jobs with clear company names")
    print("  • Actual job descriptions")
    print("="*100)
    print("📍 Web Interface: http://127.0.0.1:8000")
    print("📊 API Docs: http://127.0.0.1:8000/docs")
    print("="*100)
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)