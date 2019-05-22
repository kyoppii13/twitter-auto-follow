import os
import json
from dotenv import load_dotenv
import requests
from requests_oauthlib import OAuth1
import psycopg2
from psycopg2.extensions import QueryCanceledError
from datetime import datetime, timedelta
from time import sleep
import numpy as np

# create table twitter_user (id bigserial PRIMARY KEY, name text, screen_name text, description text, url text, followers_count integer, follows_count integer);
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

class Twitter:
  def __init__(self):
    self.API_KEY = os.environ.get("API_KEY")
    self.API_SECRET =os.environ.get("API_SECRET")
    self.ACCESS_TOKEN =os.environ.get("ACCESS_TOKEN")
    self.ACCESS_TOKEN_SECRET =os.environ.get("ACCESS_TOKEN_SECRET")
    self.auth = OAuth1(self.API_KEY, self.API_SECRET, self.ACCESS_TOKEN, self.ACCESS_TOKEN_SECRET)

  def user_search(self, keywords, from_data, to_data, next_id=False):
    # standard API
    # url = 'https://api.twitter.com/1.1/search/tweets.json'
    # payload = {'q':keywords, 'lang':'ja', 'count': 100}

    # premium API
    url = 'https://api.twitter.com/1.1/tweets/search/30day/dev.json'
    if next_id != False:
      payload = {'query':keywords, 'maxResults': 100, 'fromDate':from_data, 'toDate':to_data, 'next': next_id}
    else:
      payload = {'query':keywords, 'maxResults': 100, 'fromDate':from_data, 'toDate':to_data}

    return requests.get(url, auth=self.auth, params=payload)


  def insert_db(self, keywords, max_count=10):
    keywords = ' OR '.join(keywords)
    now = datetime.now()
    # 1ヶ月前
    start_time = now - timedelta(weeks=4)
    end_time = start_time + timedelta(hours=23, minutes=59)

    from_data = start_time.strftime('%Y%m%d%H%M')
    to_data = end_time.strftime('%Y%m%d%H%M')


    # create table twitter_user (id bigserial PRIMARY KEY, name text, screen_name text, description text, url text, followers_count integer, follows_count integer);
    res = self.user_search(keywords, from_data, to_data)
    try:
      res.raise_for_status()
    except:
      print(res.json())
    res = res.json()
    while count < max_count:
      for status in res['results']:
        user = status.get('user')
        if user:
          try:
            with self.get_connection() as conn:
              with conn.cursor() as cursor:
                cursor.execute('INSERT INTO twitter_user VALUES(%s, %s, %s, %s, %s, %s, %s)',(user['id'], user['name'], user['screen_name'], user['description'], user['url'], user['followers_count'], user['friends_count']))
              conn.commit()
          except psycopg2.errors.lookup('23505') as err:
            print(err)
        else:
          break
      next_id = res.get('next')
      if next_id:
        res = self.user_search(keywords, from_data, to_data, next_id)
      else:
        break
      sleep(np.random.normal(600,60))
      count += 1

  def create_friendship(self, user_id):
    url = 'https://api.twitter.com/1.1/friendships/create.json'
    payload = {'user_id': user_id}
    return requests.post(url, auth=self.auth, data=payload)

  def follow_users(self, max_count=100):
    with self.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM twitter_user WHERE my_friend=False')
            rows = cur.fetchall()
    if len(rows) < max_count:
      max_count = len(rows)
    for count in range(max_count):
      user = rows[count]
      # id
      user_id = user[0]
      user_name = user[1]
      res = self.create_friendship(user_id)
      try:
        res.raise_for_status()
      except:
        print(res.json())
        print("{}をフォロー出来ませんでした".format(user_name))
        continue
      try:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE twitter_user SET following_date=current_timestamp WHERE id=%s', [user_id])
                print("{}をフォローしました".format(user_name))
      except:
        print("UPDATE出来ませんでした")
      sleep(np.random.normal(300,60))




  def get_connection(self):
    return psycopg2.connect(os.environ.get("POSTGRES"))

if __name__ == '__main__':
  # 1日1回実行
  twitter = Twitter()
  keywords = ['エンジニア',
      '#エンジニアと繋がりたい']
  # twitter.insert_db(keywords)
  # 優先的に取る人決めたい
  # 100人までフォロー
  twitter.follow_users()
  # 自動解除

