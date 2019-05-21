import os
import json
from dotenv import load_dotenv
import requests
from requests_oauthlib import OAuth1
import psycopg2
from psycopg2.extensions import QueryCanceledError
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

  def user_search(self, keywords):
    url = 'https://api.twitter.com/1.1/search/tweets.json'
    payload = {'q':keywords, 'lang':'ja', 'count': 100}

    return requests.get(url, auth=self.auth, params=payload).json()

def get_connection():
  return psycopg2.connect(os.environ.get("POSTGRES"))

if __name__ == '__main__':
  twitter = Twitter()
  res = twitter.user_search('エンジニア OR #エンジニアと繋がりたい')

  # create table twitter_user (id bigserial PRIMARY KEY, name text, screen_name text, description text, url text, followers_count integer, follows_count integer);
  for status in res['statuses']:
    user = status['user']
    try:
      with get_connection() as conn:
        with conn.cursor() as cursor:
          cursor.execute('INSERT INTO twitter_user VALUES(%s, %s, %s, %s, %s, %s, %s)',(user['id'], user['name'], user['screen_name'], user['description'], user['url'], user['followers_count'], user['friends_count']))
        conn.commit()
    except psycopg2.errors.lookup('23505') as err:
      pass
