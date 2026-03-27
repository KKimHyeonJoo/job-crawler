import requests
from bs4 import BeautifulSoup
import time
import os
from datetime import datetime

class SaraminCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.job_types = {
            '정규직': '1', '계약직': '2', '인턴': '4'
        }

    def search_jobs(self, keyword=None, **filters):
        jobs = []
        api_url = "https://www.saramin.co.kr/zf_user/search/get-recruit-list"

        params = {
            'searchType': 'search',
            'recruitPage': 1,     
            'recruitSort': 'relation',   
            'recruitPageCount': 40,    
            'search_optional_item': 'y',
            'search_done': 'y',
            'panel_count': 'y',
            'preview': 'y',
            'mainSearch': 'n'
        }

        if keyword:
            params['searchword'] = keyword

        if 'job_types' in filters:
            job_type_list = [self.job_types[jt] for jt in filters['job_types'] if jt in self.job_types]
            if job_type_list:
                params['job_type'] = ','.join(job_type_list)

        try:
            response = requests.get(api_url, params=params, headers=self.headers)
            response.raise_for_status()
            json_data = response.json()

            total_count = int(json_data.get('count', '0').replace(',', ''))
            max_pages = min((total_count + 39) // 40, 5)

            print(f"총 {total_count:,}개 공고 발견! {max_pages}페이지 크롤링 예정")

            for page in range(1, max_pages + 1):
                print(f"📄 {page}/{max_pages} 페이지 수집 중...")
                params['recruitPage'] = page

                try: 
                    response = requests.get(api_url, params=params, headers=self.headers)
                    response.raise_for_status()
                    json_data = response.json()  

                    if json_data.get('innerHTML'):
                        soup = BeautifulSoup(json_data['innerHTML'], 'html.parser')
                        json_itmes = soup.find_all('div', class_='item_recruit')

                        if not json_itmes:
                            break

                        for item in json_itmes:
                            job_data = self.extract_job_info_from_api(item, keyword or '전체')
                            if job_data:
                                jobs.append(job_data)
                    else:
                        break
                    time.sleep(1)  

                except Exception as e:
                    print(f"❌ 페이지 {page} 크롤링 실패: {e}")
                    continue
        except Exception as e:
            print(f"❌ 초기 데이터 로딩 실패: {e}")
            return []
        
        return jobs
        
    def extract_job_info_from_api(self, item, keyword):
        try:
            title_elem = item.select_one('div.area_job > h2.job_tit > a')
            title = title_elem.get_text(strip=True) if title_elem else "공고명 없음"

            href = title_elem.get('href') if title_elem else ""
            link = f"https://www.saramin.co.kr{href}" if href else ""
            
            company_elem = item.select_one('div.area_corp > strong.corp_name > a')
            company = company_elem.get_text(strip=True) if company_elem else "회사명 없음"

            deadline_elem = item.select_one('div.area_job > div.job_date > span.date')
            deadline = deadline_elem.get_text(strip=True) if deadline_elem else "마감일 없음"

            condition_elem = item.select('div.area_job > div.job_condition > span')

            location = "지역 없음"  
            career = "경력 없음"
            education = "학력 없음"  

            if len(condition_elem) > 0:
                location_elem = condition_elem[0].select('a')
                location_list = [loc.get_text(strip=True) for loc in location_elem]
                location = " ".join(location_list) if len(location_list) >= 2 else (location_list[0] if location_list else "지역 없음")

            if len(condition_elem) > 1: career = condition_elem[1].get_text(strip=True)
            if len(condition_elem) > 2: education = condition_elem[2].get_text(strip=True)

            return {
                'keyword': keyword,
                'title': title,
                'company': company,
                'location': location,
                'career': career,
                'education': education,
                'deadline': deadline,
                'link': link,
                'crawled_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            return None
    
    def send_to_n8n_webhook(self, jobs, webhook_url):
        if not jobs or not webhook_url:
            print("⚠️ Webhook URL이 설정되지 않았습니다.")
            return

        print(f"\n🚀 n8n Webhook으로 데이터 전송 시작 (총 {len(jobs)}개)")
        success_count = 0
        
        for job in jobs:
            try:
                response = requests.post(
                    webhook_url, 
                    json=job,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    success_count += 1
            except Exception as e:
                print(f"❌ [{job.get('title')}] n8n 전송 실패: {e}")
                
        print(f"✅ 총 {success_count}/{len(jobs)}개 공고 n8n 전송 완료!")

    def run_n8n_crawler(self, webhook_url=None):
        print("🚀 크롤링 시작!")

        search_configs = [
            {'keyword': 'ai 개발자', 'job_types': ['정규직']},
            {'keyword': 'ai 엔지니어', 'job_types': ['정규직']},
            {'keyword': '데이터 엔지니어', 'job_types': ['정규직']}
        ]

        all_jobs = []
        for config in search_configs:
            print(f"\n📋 '{config['keyword']}' 검색 중...")
            keyword = config.pop('keyword') 
            jobs = self.search_jobs(keyword=keyword, **config)
            all_jobs.extend(jobs)

        unique_jobs = []
        seen_links = set()
        for job in all_jobs:
            if job['link'] not in seen_links:
                unique_jobs.append(job)
                seen_links.add(job['link'])

        strict_filtered_jobs = []
        target_keywords = ['ai개발자', 'ai엔지니어', '데이터엔지니어']
        
        for job in unique_jobs:
            clean_title = job['title'].lower().replace(" ", "")
            if any(target in clean_title for target in target_keywords):
                strict_filtered_jobs.append(job)

        print(f"\n🎉 최종 핵심 공고 선별 완료: {len(strict_filtered_jobs)}개")

        if webhook_url and strict_filtered_jobs:
            self.send_to_n8n_webhook(strict_filtered_jobs, webhook_url)
        
        return strict_filtered_jobs

if __name__ == "__main__":
    crawler = SaraminCrawler()
    print("\n" + "="*60)
    print("🎯 n8n 전용 AI/Data 채용공고 파이프라인")
    print("="*60)

    # 오직 n8n 웹훅 주소만 가져옵니다. (이메일 환경변수 삭제)
    n8n_webhook_url = os.environ.get('N8N_WEBHOOK_URL') 
    crawler.run_n8n_crawler(webhook_url=n8n_webhook_url)
    print(f"\n📊 파이프라인 실행 완료")