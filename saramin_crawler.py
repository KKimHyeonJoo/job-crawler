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
                'title': title,
                'company': company,
                'location': location,
                'career': career,
                'education': education,
                'deadline': deadline,
                'link': link
            }
        except Exception as e:
            return None
    
    # ✨ 변경된 부분: 공고를 하나씩 쏘지 않고, 'jobs'라는 큰 박스에 담아 한 번에 쏩니다! ✨
    def send_to_n8n_webhook(self, jobs, webhook_url):
        if not jobs or not webhook_url:
            print("⚠️ Webhook URL이 설정되지 않았거나 데이터가 없습니다.")
            return

        print(f"\n🚀 n8n Webhook으로 데이터 [한 번에] 전송 시작 (총 {len(jobs)}개)")
        try:
            # 전체 공고 리스트를 'jobs'라는 이름의 딕셔너리로 감싸서 보냅니다.
            payload = {"jobs": jobs} 
            response = requests.post(
                webhook_url, 
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            if response.status_code == 200:
                print(f"✅ 총 {len(jobs)}개 공고 리스트 n8n 전송 완료!")
            else:
                print(f"❌ 전송 실패: {response.status_code}")
        except Exception as e:
            print(f"❌ n8n 전송 실패: {e}")

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
    print("🎯 n8n 전용 AI/Data 일괄 평가 파이프라인")
    print("="*60)

    n8n_webhook_url = os.environ.get('N8N_WEBHOOK_URL') 
    crawler.run_n8n_crawler(webhook_url=n8n_webhook_url)
    print(f"\n📊 파이프라인 실행 완료")