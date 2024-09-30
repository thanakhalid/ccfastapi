from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import pandas as pd
from io import BytesIO
import time
import json
import requests

app = FastAPI()
templates = Jinja2Templates(directory="templates")

class ProfileFetcher:
    URL = 'https://curiouscat.live/api/v2.1/profile?username={}&max_timestamp={}'
    DELAY = 1

    def get_oldest_saved_timestamp(self, info):
        if len(info['posts']) == 0:
            return int(time.time())
        timestamps = (int(x['post']['timestamp']) for x in info['posts'])
        return min(timestamps)

    def read_file(self, filename):
        if not Path(filename).exists():
            return {'posts': []}
        with open(filename) as f:
            return json.load(f)

    def get_responses(self, username, timestamp):
        url = self.URL.format(username, timestamp)
        res = requests.get(url)
        res_dict = res.json()
        posts = res_dict['posts']
        res_dict.pop('posts', None)
        return posts, res_dict, len(posts) == 0

    def extract_questions_and_answers(self, data):
        posts = data.get("posts", [])
        questions_answers = []
        for item in posts:
            if item.get("type") == "post":
                post_data = item.get("post", {})
                question = post_data.get("comment")
                answer = post_data.get("reply")
                questions_answers.append({
                    "Question": question,
                    "Answer": answer
                })
        return questions_answers

    def create_excel_file(self, data):
        """Creates an Excel file in memory and returns it as a BytesIO object."""
        df = pd.DataFrame(data)
        excel_file = BytesIO()
        df.to_excel(excel_file, index=False, engine='openpyxl')
        excel_file.seek(0)  # Move to the beginning of the BytesIO buffer
        return excel_file

fetcher = ProfileFetcher()

@app.get("/")
async def read_form(request: Request):
    return templates.TemplateResponse("base.html", {"request": request})

@app.post("/download/")
async def download_file(request: Request, user_input: str = Form(...)):
    username = user_input
    filename = f'{username}.json'

    info = fetcher.read_file(filename)
    finish = False
    timestamp = fetcher.get_oldest_saved_timestamp(info) - 1
    results = info['posts']

    while not finish:
        posts, res_dict, finish = fetcher.get_responses(username, timestamp)
        not_posts = [post for post in posts if post['type'] != 'post']
        posts = [post for post in posts if post not in not_posts]
        results.extend(posts)

        if not finish:
            timestamp = int(posts[-1]['post']['timestamp']) - 1
        info.update(res_dict)
        time.sleep(fetcher.DELAY)

    info['posts'] = results
    questions_answers = fetcher.extract_questions_and_answers(info)
    excel_file = fetcher.create_excel_file(questions_answers)

    response = StreamingResponse(
        excel_file,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response.headers["Content-Disposition"] = f"attachment; filename={username}_questions_answers.xlsx"
    return response
