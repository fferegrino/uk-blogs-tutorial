import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

data_dir = Path('data')
data_dir.mkdir(exist_ok=True)


try:
    with open(data_dir / "cutoff_date.txt") as f:
        CUTOFF_DATE = datetime.fromisoformat(f.read())
except:
    CUTOFF_DATE = datetime.now() - timedelta(days=365*100)

def parse_entry(entry):
    title = entry.find('h3').text
    anchors = entry.find_all('a')
    link = anchors[0]['href']
    time = entry.find('time')['datetime']
    blog = anchors[1].text
    blog_link = anchors[1]['href']
    description = entry.find('p').text

    entry_dict = {
        'title': title,
        'link': link,
        'time': datetime.strptime(time[:19], '%Y-%m-%dT%H:%M:%S'),
        'blog': blog,
        'blog_link': blog_link,
        'description': description
    }

    return entry_dict


def fetch_entries_for_page(page_number, cutoff_date):
    page_response = requests.get(f'https://www.blog.gov.uk/all-posts/page/{page_number}')
    page_soup = BeautifulSoup(page_response.text, "html.parser")
    entry_list = page_soup.find('ul', {'class':'blogs-list'})
    entry_list_elements = entry_list.find_all('li')
    no_results_li = entry_list.find('li', {'class':'noresults'})

    entries = []
    if no_results_li:
        return entries

    for entry in entry_list_elements:
        parsed_entry = parse_entry(entry)
        if parsed_entry['time'] < cutoff_date:
            break
        entries.append(parsed_entry)
    return entries


all_current_entries = []

for page in range(1, 10_000):
    print(f"Web scrapping page {page}")
    entries = fetch_entries_for_page(page, CUTOFF_DATE)
    if not entries:
        break
    all_current_entries.extend(entries)


def parse_article_metadata(article_soup):
    article_tag = article_soup.find('article')
    article_title = article_tag.find('h1').text
    authors = article_tag.find_all('a', {'class': 'author'})
    article_authors = [author.text for author in authors]
    article_posted_on = article_tag.find('time')['datetime']
    categories = article_tag.find_all('a', {'rel': 'category'})
    article_categories = [category.text for category in categories]
    article_categories

    article_metadata_data = {
        'title': article_title,
        'authors': article_authors,
        'posted_on': datetime.strptime(article_posted_on[:19], '%Y-%m-%dT%H:%M:%S'),
        'categories': article_categories
    }

    return article_metadata_data

consumable_tags = { "p", "h2", "h3", "h4" }

def parse_article_content(article_soup):
    entry_container = article_soup.find('div', {'class': 'entry-content'})
    content = []
    for child in entry_container.children:
        if child.name in consumable_tags:
            if child.text:
                content.append({'content': child.text, 'tag': child.name})
        else:
            if child.name:
              # print(f"Unknown tag: {child.name}")
              pass

    return content


def fetch_article(article_entry):
    article_response = requests.get(article_entry['link'])
    article_soup = BeautifulSoup(article_response.text, "html.parser")
    article_metadata = parse_article_metadata(article_soup)
    article_content = parse_article_content(article_soup)

    article_metadata['content'] = article_content
    article_metadata['link'] = article_entry['link']
    article_metadata['blog'] = article_entry['blog']
    article_metadata['blog_link'] = article_entry['blog_link']
    article_metadata['description'] = article_entry['description']

    return article_metadata


full_articles = []

for entry in all_current_entries:
    full_articles.append(fetch_article(entry))

def bucket_articles_weekly(articles):
    weekly_buckets = defaultdict(list)
    sorted_articles = sorted(articles, key=lambda x: x['posted_on'], reverse=True)

    for article in sorted_articles:
        article_date = article['posted_on'].date()
        start_of_week = article_date - timedelta(days=article_date.weekday())
        weekly_buckets[start_of_week].append(article)

    sorted_weekly_buckets = dict(sorted(weekly_buckets.items(), reverse=True))

    return sorted_weekly_buckets


class DateTimeCodec(json.JSONEncoder):
    def __init__(self, datetime_fields=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datetime_fields = set(datetime_fields or [])

    def default(self, obj):
        return obj.isoformat() if isinstance(obj, datetime) else super().default(obj)

    def decode(self, obj):
        return {k: datetime.fromisoformat(v) if k in self.datetime_fields and isinstance(v, str) else v
                for k, v in obj.items()}
    
def write_weekly_data(date, records):
    datetime_fields = ['posted_on']
    target_file = data_dir / f'{date}.json'
    if target_file.exists():
        with open(target_file) as f:
            current_records = json.load(f, object_hook=DateTimeCodec(datetime_fields).decode)
        existing_record_links = {
            record['link'] for record in current_records
        }
    else:
        existing_record_links = set()
        current_records = []

    for new_record in records:
        if new_record['link'] in existing_record_links:
            continue
        existing_record_links.add(new_record['link'])
        current_records.append(new_record)

    current_records = sorted(current_records, key=lambda x: x['posted_on'], reverse=True)
    with open(target_file, 'w') as f:
        json.dump(current_records, f, indent=4, cls=DateTimeCodec, datetime_fields=datetime_fields)


bucketed_articles = bucket_articles_weekly(full_articles)

for week_start, week_articles in bucketed_articles.items():
    write_weekly_data(week_start, week_articles)

with open(data_dir / 'cutoff_date.txt', 'w') as f:
    f.write(full_articles[0]['posted_on'].isoformat())

print("Data scraped successfully!")
