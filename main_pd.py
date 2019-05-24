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
import argparse
import glob
import pandas as pd
import pickle

# create table twitter_user (id bigserial PRIMARY KEY, name text, screen_name text, description text, url text, followers_count integer, follows_count integer);
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

class Twitter:
  def __init__(self, keywords, create_json, create_pd):
    self.API_KEY = os.environ.get("API_KEY")
    self.API_SECRET =os.environ.get("API_SECRET")
    self.ACCESS_TOKEN =os.environ.get("ACCESS_TOKEN")
    self.ACCESS_TOKEN_SECRET =os.environ.get("ACCESS_TOKEN_SECRET")
    self.MY_TWITTER_ID = os.environ.get('MY_TWITTER_ID')
    self.auth = OAuth1(self.API_KEY, self.API_SECRET, self.ACCESS_TOKEN, self.ACCESS_TOKEN_SECRET)
    self.keywords = keywords.split(',')
    self.json_path = 'json'
    self.pandas_path = 'pandas'
    self.follower_ids = []
    self.follow_ids = []
    self.data_df = False
    os.makedirs(self.json_path, exist_ok=True)
    os.makedirs(self.pandas_path, exist_ok=True)
    # フォロワーの取得
    self.get_follower()
    # フォローの取得
    self.get_follow()
    if create_json:
      self.create_users_json()
    if create_pd:
      self.create_pd()

  def get_connection(self):
    return psycopg2.connect(os.environ.get("POSTGRES"))

  def user_search(self, keywords, from_data, to_data, next_id=False):
    # premium API
    url = 'https://api.twitter.com/1.1/tweets/search/30day/dev.json'
    if next_id != False:
      payload = {'query':keywords, 'maxResults': 100, 'fromDate':from_data, 'toDate':to_data, 'next': next_id}
    else:
      payload = {'query':keywords, 'maxResults': 100, 'fromDate':from_data, 'toDate':to_data}

    return requests.get(url, auth=self.auth, params=payload)

  # create table twitter_user (id bigserial PRIMARY KEY, name text, screen_name text, description text, url text, followers_count integer, follows_count integer);
  def create_users_json(self, max_exection=2):
    keywords = ' OR '.join(self.keywords)
    now = datetime.now()
    # 1ヶ月前
    start_time = now - timedelta(weeks=4)
    end_time = start_time + timedelta(hours=23, minutes=59)

    from_data = start_time.strftime('%Y%m%d%H%M')
    to_data = end_time.strftime('%Y%m%d%H%M')
    count = 0 users = []
    res = self.user_search(keywords, from_data, to_data)
    res.raise_for_status()
    while count < max_exection:
      print("ユーザ情報収集中:{}/{}".format(count,max_exection))
      res = res.json()
      users.extend([item for item in res['results']])

      next_id = res.get('next')
      if next_id:
        res = self.user_search(keywords, from_data, to_data, next_id)
      else:
        break
      sleep(np.random.normal(10,5))
      count += 1

    if len(users) != 0:
      with open(os.path.join(self.json_path,'user_list_{}.json'.format(now.strftime('%Y%m%d%H%M'))), 'w') as f:
        json.dump(users, f)


  def create_friendship(self, user_id):
    url = 'https://api.twitter.com/1.1/friendships/create.json'
    payload = {'user_id': user_id}
    return requests.post(url, auth=self.auth, data=payload)

  def destroy_friendship(self, user_id):
    url = 'https://api.twitter.com/1.1/friendships/destroy.json'
    payload = {'user_id': user_id}
    return requests.post(url, auth=self.auth, data=payload)

  def follow_users(self, max_count=100):
    if len(rows) < max_count:
      max_count = len(rows)
    now = datetime.now()
    for count in range(max_count):
      follow_kouho = self.data_df[(self.data_df['follow_time'] <= now-timedelta(weeks=7)) & ~(self.data_df['followed'])]
      # id
      follow_id = follow_kouho['id']
      follow_name = follow_kouho['user_name']
      res = self.create_friendship(follow_id)
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

  def follow_users(self, max_count=100):
    with self.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM twitter_user WHERE following_date IS NULL')
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


  def destroy_users(self, max_count=100):
    with self.get_connection() as conn:
        with conn.cursor() as cur:
          # 1週間より前にフォロー, かつno_removeがTrueじゃない
          cur.execute("SELECT * FROM twitter_user WHERE following_date < now() - interval '1 hour'")
          rows = cur.fetchall()

    if len(rows) < max_count:
      max_count = len(rows)

    for count in range(max_count):
      user = rows[count]
      # id
      user_id = user[0]
      user_name = user[1]
      res = self.destroy_friendship(user_id)
      try:
        res.raise_for_status()
      except:
        print(res.json())
        print("{}をフォロー解除出来ませんでした".format(user_name))
        continue
      try:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE twitter_user SET following_date=current_timestamp WHERE id=%s', [user_id])
                print("{}をフォロー解除しました".format(user_name))
      except:
        print("UPDATE出来ませんでした")
      sleep(np.random.normal(300,60))

  def create_pd(self):
    all_user_data = []
    for i in glob.glob('json/*.json'):
      with open(i, 'r') as f:
        j = json.load(f)
      for tweet in j:
        user = {}
        _user = tweet['user']
        user['id'] = _user['id']
        user['name'] = _user['name']
        user['screen_name'] = _user['screen_name']
        user['description'] = _user['description']
        user['url'] = _user['url']
        user['followers_count'] = _user['followers_count']
        user['follow_count'] = _user['friends_count']
        user['hit_tweet_text'] = tweet['text']
        user['hit_tweet_created_at'] = tweet['created_at']
        user['follow_time'] = False
        all_user_data.append(user)

    data_df = pd.DataFrame(all_user_data)
    self.data_df = data_df

    data_df['followed'] = data_df['id'].apply(lambda x: x in self.follower_ids)

    with open(os.path.join(self.pandas_path, 'user.pkl'), 'wb') as f:
        pickle.dump(data_df, f)

  def get_follower(self):
    url = 'https://api.twitter.com/1.1/followers/ids.json'
    payload = {'screen_name': self.MY_TWITTER_ID}
    res = requests.get(url, auth=self.auth, params=payload)
    while True:
      res.raise_for_status()
      res = res.json()
      self.follower_ids.extend(res['ids'])
      next_cursor = res['next_cursor']
      if next_cursor != 0:
        payload['cursor'] = next_cursor
        res = requests.get(url, auth=self.auth, params=payload)
      else:
        break

  def get_follow(self):
    url = 'https://api.twitter.com/1.1/friends/ids.json'
    payload = {'screen_name': self.MY_TWITTER_ID}
    res = requests.get(url, auth=self.auth, params=payload)
    while True:
      res.raise_for_status()
      res = res.json()
      self.follow_ids.extend(res['ids'])
      next_cursor = res['next_cursor']
      if next_cursor != 0:
        payload['cursor'] = next_cursor
        res = requests.get(url, auth=self.auth, params=payload)
      else:
        break


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--create-json', action='store_true')
  parser.add_argument('--keywords', type=str, required=True)
  parser.add_argument('--create-pd', action='store_true')
  args = parser.parse_args()
  # 1日1回実行
  twitter = Twitter(args.keywords, args.create_json, args.create_pd)
  # 優先的に取る人決めたい
  # 100人までフォロー
  # twitter.follow_users()
  # 自動解除
  # twitter.destroy_users()
  # 自分の情報
    # フォローしてるかどうか

