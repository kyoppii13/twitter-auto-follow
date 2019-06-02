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
import re
import pickle
import pandas as pd

# create table twitter_user (id bigserial PRIMARY KEY, name text, screen_name text, description text, url text, followers_count integer, follows_count integer);
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

class Twitter:
  def __init__(self, keywords, get_tweet, create_follow, destroy_follow, pd_update, get_follow_follower):
    self.API_KEY = os.environ.get("API_KEY")
    self.API_SECRET = os.environ.get("API_SECRET")
    self.ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
    self.ACCESS_TOKEN_SECRET = os.environ.get("ACCESS_TOKEN_SECRET")
    self.MY_TWITTER_ID = os.environ.get('MY_TWITTER_ID')
    self.auth = OAuth1(self.API_KEY, self.API_SECRET, self.ACCESS_TOKEN, self.ACCESS_TOKEN_SECRET)
    self.keywords = keywords.split(',')
    self.json_path = 'json'
    self.pickle_path = 'pickle'
    self.follower_ids = []
    self.follow_ids = []
    self.data_df = False
    self.now = datetime.now()
    self.pd_update = pd_update
    os.makedirs(self.json_path, exist_ok=True)
    os.makedirs(self.pickle_path, exist_ok=True)
    # ユーザ情報取得
    if get_tweet:
      self.create_json()
      self.insert_db()
    if get_follow_follower:
      # フォローの取得
      self.get_follow()
      # フォロワーの取得
      self.get_follower()
    if pd_update:
      self.convert_pd()
    if create_follow:
      self.create_follow()
    if destroy_follow:
      self.destroy_follow()

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

  def create_json(self, max_exection=10):
    keywords = ' OR '.join(self.keywords)
    # 1ヶ月前
    start_time = self.now - timedelta(weeks=4)
    end_time = start_time + timedelta(hours=23, minutes=59)

    from_data = start_time.strftime('%Y%m%d%H%M')
    to_data = end_time.strftime('%Y%m%d%H%M')
    count = 0
    users = []
    res = self.user_search(keywords, from_data, to_data)
    try:
      res.raise_for_status()
    except:
      with open('error.log', 'a') as f:
        f.write(res.json()['errors'][0]['message'])
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
      with open(os.path.join(self.json_path,'user_list_{}.json'.format(self.now.strftime('%Y%m%d%H%M'))), 'w') as f:
        json.dump(users, f)


  def insert_db(self, max_count=10):
    # create table twitter_user (id bigserial PRIMARY KEY, name text, screen_name text, description text, url text, followers_count integer, follows_count integer);
    latest_date = sorted([re.search('[0-9]+',i).group() for i in glob.glob(self.json_path + '/*.json')])[-1]
    j = os.path.join(self.json_path, 'user_list_%s.json' % latest_date)
    with open(j) as f:
      res = json.load(f)
    for status in res:
      user = status.get('user')
      if user:
        try:
          with self.get_connection() as conn:
            with conn.cursor() as cursor:
              cursor.execute('INSERT INTO twitter_user(id, name, screen_name, description, url, followers_count, follows_count, tweet, no_target) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, False)',(user['id'], user['name'], user['screen_name'], user['description'], user['url'], user['followers_count'], user['friends_count'], status['text']))
            conn.commit()
        except psycopg2.errors.lookup('23505') as err:
          # print(err)
          with self.get_connection() as conn:
            with conn.cursor() as cursor:
              cursor.execute('UPDATE twitter_user SET name=%s, screen_name=%s, description=%s, url=%s, followers_count=%s, follows_count=%s, tweet=%s WHERE id=%s',(user['name'], user['screen_name'], user['description'], user['url'], user['followers_count'], user['friends_count'], status['text'], user['id']))
            conn.commit()
          print("%sの情報をアップデートしました" % user['name'])
      else:
        break

  def create_friendship(self, user_id):
    url = 'https://api.twitter.com/1.1/friendships/create.json'
    payload = {'user_id': user_id}
    return requests.post(url, auth=self.auth, data=payload)

  def destroy_friendship(self, user_id):
    url = 'https://api.twitter.com/1.1/friendships/destroy.json'
    payload = {'user_id': user_id}
    return requests.post(url, auth=self.auth, data=payload)

  def create_follow(self, max_count=100):
    with self.get_connection() as conn:
      with conn.cursor() as cur:
        cur.execute('SELECT * FROM twitter_user WHERE following_date is NULL')
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
        with open('error.log', 'a') as f:
          f.write(res.json()['errors'][0]['message'])
        print("{}をフォロー出来ませんでした".format(user_name))
        continue
      try:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE twitter_user SET following_date=current_timestamp WHERE id=%s', [user_id])
                print("{}をフォローしました".format(user_name))
      except:
        print("UPDATE出来ませんでした")
      sleep(np.random.normal(60,10))

  def get_follower(self):
    url = 'https://api.twitter.com/1.1/followers/list.json'
    payload = {'screen_name': self.MY_TWITTER_ID, 'count': 200}
    res = requests.get(url, auth=self.auth, params=payload)
    users = []
    while True:
      res.raise_for_status()
      res = res.json()
      users.extend(res['users'])
      self.follower_ids.extend([user['id'] for user in res['users']])
      next_cursor = res['next_cursor']
      if next_cursor != 0:
        payload['cursor'] = next_cursor
        res = requests.get(url, auth=self.auth, params=payload)
      else:
        break
    try:
      with self.get_connection() as conn:
        with conn.cursor() as cur:
          for user_id in self.follower_ids:
            cur.execute('UPDATE twitter_user SET followed=True WHERE id=%s', [user_id])
      print("followedアップデート完了")
    except:
      print("データベースをアップデート出来ませんでした")

    with open(os.path.join(self.json_path,'follower_list_{}.json'.format(self.now.strftime('%Y%m%d%H%M'))), 'w') as f:
      json.dump(users, f)

  def get_follow(self):
    print("フォロー取得開始")
    url = 'https://api.twitter.com/1.1/friends/list.json'
    payload = {'screen_name': self.MY_TWITTER_ID, 'count': 200}

    res = requests.get(url, auth=self.auth, params=payload)
    users = []

    while True:
      sleep(np.random.normal(60,10))
      try:
        res.raise_for_status()
      except:
        with open('error.log', 'a') as f:
          f.write(res.json()['errors'][0]['message'])
      res = res.json()
      users.extend(res['users'])
      self.follow_ids.extend([user['id'] for user in res['users']])
      next_cursor = res['next_cursor']
      if next_cursor != 0:
        payload['cursor'] = next_cursor
        res = requests.get(url, auth=self.auth, params=payload)
      else:
        break

    last_date = max([int(re.search('[0-9]+',i).group()) for i in glob.glob(os.path.join(self.json_path,'follow_list_*.json'))])
    with open(os.path.join(self.json_path, "follow_list_{}.json".format(last_date)), 'r') as f:
      follow_list_lastday = json.load(f)
    follow_id_lastday = [i['id'] for i in follow_list_lastday]
    follow_id_today = [i['id'] for i in users]
    self_remove_follow = list(set(follow_id_lastday) - set(follow_id_today))
    try:
      with self.get_connection() as conn:
        with conn.cursor() as cur:
          for user_id in self_remove_follow:
            cur.execute('UPDATE twitter_user SET no_target=True WHERE id=%s', [user_id])
            print(user_id)
          print("フォローの差分UPDATE完了")
    except:
      print("フォローの差分UPDATE出来ませんでした")
    with open(os.path.join(self.json_path,'follow_list_{}.json'.format(self.now.strftime('%Y%m%d%H%M'))), 'w') as f:
      json.dump(users, f)
    print("フォローアップデート完了")

  def destroy_follow(self, max_count=150):
    with self.get_connection() as conn:
        with conn.cursor() as cur:
          # 3日前より前にフォロー
          # 自分でフォローしたのはfollowing_dateが空
          cur.execute("SELECT * FROM twitter_user WHERE following_date < now() - interval '3 day' and followed=False and no_target")
          rows = cur.fetchall()


    if len(rows) < max_count:
      max_count = len(rows)

    destroy_count = 0
    for count in range(max_count):
      user = rows[count]
      # id
      user_id = user[0]
      user_name = user[1]
      res = self.destroy_friendship(user_id)
      try:
        res.raise_for_status()
      except:
        with open('error.log', 'a') as f:
          f.write(res.json()['errors'][0]['message'])
        continue
      try:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE twitter_user SET no_target=True WHERE id=%s', [user_id])
                print("{}をフォロー解除しました".format(user_name))
                destroy_count+=1
      except:
        print("UPDATE出来ませんでした")
      sleep(np.random.normal(60,10))
    print("%3s人フォロー解除しました" % destroy_count)

  def convert_pd(self):
    all_follower_list = []
    for j in glob.glob(os.path.join(self.json_path, 'follower_list_*.json')):
      d = {}
      with open(j, 'r') as f:
        follower_list_day = json.load(f)
      date = re.search('[0-9]+',j).group()
      d['date'] = datetime.strptime(date, "%Y%m%d%H%M")
      d['follower_count'] = len(follower_list_day)
      all_follower_list.append(d)
    all_follower_list = pd.DataFrame(all_follower_list)
    with open(os.path.join(self.pickle_path, 'follower.pkl'), 'wb') as f:
      pickle.dump(all_follower_list, f)

    all_follow_list = []
    for j in glob.glob('json/follow_list_*.json'):
      d = {}
      with open(j, 'r') as f:
        follow_list_day = json.load(f)
      date = re.search('[0-9]+',j).group()
      d['date'] = datetime.strptime(date, "%Y%m%d%H%M")
      d['follow_count'] = len(follower_list_day)
      all_follow_list.append(d)
    all_follow_list = pd.DataFrame(all_follow_list)
    with open(os.path.join(self.pickle_path, 'follow.pkl'), 'wb') as f:
      pickle.dump(all_follow_list, f)

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--keywords', type=str, required=True)
  parser.add_argument('--get-tweet', action='store_false')
  parser.add_argument('--create-follow', action='store_false')
  parser.add_argument('--destroy-follow', action='store_false')
  parser.add_argument('--pd-update', action='store_false')
  parser.add_argument('--get-follow-follower', action='store_false')
  args = parser.parse_args()
  # 1日1回実行
  twitter = Twitter(args.keywords, args.get_tweet, args.create_follow, args.destroy_follow, args.pd_update, args.get_follow_follower) # 優先的に取る人決めたい
  # 100人までフォロー

