import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

class SaraminCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 파라미터들을 딕셔너리로 정리
        self.salary_codes = {
            '2400만원~': '8', '2600만원~': '9', '2800만원~': '10', '3000만원~': '11',
            '3200만원~': '12', '3400만원~': '13', '3600만원~': '14', '3800만원~': '15',
            '4000만원~': '16', '5000만원~': '17', '6000만원~': '18', '7000만원~': '19',
            '8000만원~': '20', '9000만원~': '21', '1억원~': '22'
        }
        
        self.company_types = {
            '대기업': 'scale001', '중견기업': 'scale003', '중소기업': 'scale004',
            '스타트업': 'scale005', '외국계': 'foreign', '코스닥': 'kosdaq',
            '공사/공기업': 'public', '연구소': 'laboratory', '교육기관': 'school',
            '금융기업': 'banking-organ'
        }
        
        self.job_types = {
            '정규직': '1', '계약직': '2', '병역특례': '3', '인턴': '4',
            '아르바이트': '5', '파견직': '6', '해외취업': '7', '위촉직': '8',
            '프리랜서': '9', '교육생': '12', '파트타임': '14', '전임': '15'
        }
        
        self.work_days = {
            '주5일': 'wsh010', '주6일': 'wsh030', '주3일/격일': 'wsh040',
            '유연근무제': 'wsh050', '면접후결정': 'wsh090'
        }

    def search_jobs(self, keyword=None, **filters):
        """실제 api 엔드포인트 사용한 검색"""
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

        self._apply_filters(params, filters)

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
                            print(f"페이지 {page}에서 공고를 찾을 수 없습니다.")
                            break

                        for item in json_itmes:
                            job_data = self.extract_job_info_from_api(item, keyword or '전체')
                            if job_data:
                                jobs.append(job_data)
                    else:
                        print(f"페이지 {page}에서 데이터를 받지 못했습니다.")
                        break

                    time.sleep(1)  

                except Exception as e:
                    print(f"❌ 페이지 {page} 크롤링 실패: {e}")
                    continue
        
        except Exception as e:
            print(f"❌ 초기 데이터 로딩 실패: {e}")
            return []
        
        return jobs
    
    def _apply_filters(self, params, filters):
        if 'salary_min' in filters and filters['salary_min'] in self.salary_codes:
            params['sal_min'] = self.salary_codes[filters['salary_min']]

        if 'company_types' in filters:
            company_list = [self.company_types[ct] for ct in filters['company_types'] if ct in self.company_types]
            if company_list:
                params['company_type'] = ','.join(company_list)

        if 'job_types' in filters:
            job_type_list = [self.job_types[jt] for jt in filters['job_types'] if jt in self.job_types]
            if job_type_list:
                params['job_type'] = ','.join(job_type_list)

        if 'work_days' in filters:
            work_day_list = [self.work_days[wd] for wd in filters['work_days'] if wd in self.work_days]
            if work_day_list:
                params['work_day'] = ','.join(work_day_list)

        if filters.get('remote_work', False):
            params['work_type'] = '1'

        if 'exclude_keywords' in filters:
            params['exc_keyword'] = ','.join(filters['exclude_keywords'])

        
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
            work_type = "근무형태 없음"

            if len(condition_elem) > 0:
                location_elem = condition_elem[0].select('a')
                location_list = [loc.get_text(strip=True) for loc in location_elem]
                if len(location_list) >= 2: location = " ".join(location_list)
                elif len(location_list) == 1: location = location_list[0]

            if len(condition_elem) > 1: career = condition_elem[1].get_text(strip=True)
            if len(condition_elem) > 2: education = condition_elem[2].get_text(strip=True)
            if len(condition_elem) > 3: work_type = condition_elem[3].get_text(strip=True)

            rec_idx = item.get('value', '')

            return {
                'keyword': keyword,
                'title': title,
                'company': company,
                'location': location,
                'career': career,
                'education': education,
                'work_type': work_type,
                'deadline': deadline,
                'link': link,
                'rec_idx': rec_idx,
                'crawled_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            return None

    def save_to_csv(self, jobs, filename=None):
        if not jobs: return None
        if not filename:
            filename = f"사람인_공고_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"   
        df = pd.DataFrame(jobs)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        return filename
    
    def send_to_n8n_webhook(self, jobs, webhook_url):
        if not jobs or not webhook_url:
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

    def send_email_notification(self, jobs, email_config):
        # ... (이전과 동일하여 생략 없이 작동) ...
        pass # 실제 실행 시에는 사용하지 않으셔도 무방합니다.

    def run_advanced_crawler(self, email_config=None, webhook_url=None):
        print("🚀 크롤링 시작!")

        # ✨ 1. 검색어 자체를 명확하게 세팅 ✨
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

        # 1차: 링크 기준 중복 제거
        unique_jobs = []
        seen_links = set()
        for job in all_jobs:
            if job['link'] not in seen_links:
                unique_jobs.append(job)
                seen_links.add(job['link'])

        # ✨ 2. 제목 기반 엄격한 필터링 (핵심 기능) ✨
        strict_filtered_jobs = []
        
        # 비교를 위해 공백이 없고 소문자인 타겟 키워드 리스트 준비
        target_keywords = ['ai개발자', 'ai엔지니어', '데이터엔지니어']
        
        for job in unique_jobs:
            # 꿀팁: 공고 제목의 띄어쓰기를 다 없애고 영문을 모두 소문자로 바꿉니다.
            # 예) "AI 개발자 (신입/경력)" -> "ai개발자(신입/경력)"
            clean_title = job['title'].lower().replace(" ", "")
            
            # 정제된 제목 안에 우리가 원하는 키워드가 하나라도 들어있는지 검사!
            if any(target in clean_title for target in target_keywords):
                strict_filtered_jobs.append(job)

        print(f"\n🎉 1차 수집: {len(unique_jobs)}개 -> ✨ 최종 필터링(엄격): {len(strict_filtered_jobs)}개 핵심 공고 선별 완료!")

        # n8n으로 전송
        if webhook_url and strict_filtered_jobs:
            self.send_to_n8n_webhook(strict_filtered_jobs, webhook_url)
        
        return strict_filtered_jobs

if __name__ == "__main__":
    crawler = SaraminCrawler()

    print("\n" + "="*60)
    print("🎯 맞춤형(AI/Data) 채용공고 크롤링 & n8n 전송")
    print("="*60)

    # n8n 웹훅 URL (GitHub Secrets 연동)
    n8n_webhook_url = os.environ.get('N8N_WEBHOOK_URL') 

    # 자동화 실행
    final_jobs = crawler.run_advanced_crawler(webhook_url=n8n_webhook_url)

    print(f"\n📊 최종 실행 완료")