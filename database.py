import os
import sqlite3
import uuid
from urllib.parse import urlparse

import bcrypt


class BlacklistedWebsite:
    def __init__(self, blacklist_id, url):
        self.id = blacklist_id
        self.netloc = url


class Website:

    def __init__(self, url, logged_ip, logged_useragent, last_modified=None, website_id=None):
        self.url = url
        self.logged_ip = logged_ip
        self.logged_useragent = logged_useragent
        self.last_modified = last_modified
        self.id = website_id


class ApiClient:

    def __init__(self, token, name):
        self.token = token
        self.name = name


class Database:

    def __init__(self, db_path):

        self.db_path = db_path

        if not os.path.exists(db_path):
            self.init_database()

    def init_database(self):

        with open("init_script.sql", "r") as f:
            init_script = f.read()

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(init_script)
            conn.commit()

    def update_website_date_if_exists(self, website_id):

        with sqlite3.connect(self.db_path) as conn:

            cursor = conn.cursor()
            cursor.execute("UPDATE Website SET last_modified=CURRENT_TIMESTAMP WHERE id=?", (website_id, ))
            conn.commit()

    def insert_website(self, website: Website):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO Website (url, logged_ip, logged_useragent) VALUES (?,?,?)",
                           (website.url, str(website.logged_ip), str(website.logged_useragent)))
            cursor.execute("SELECT LAST_INSERT_ROWID()")

            website_id = cursor.fetchone()[0]
            conn.commit()

        return website_id

    def get_website_by_url(self, url):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id, url, logged_ip, logged_useragent, last_modified FROM Website WHERE url=?",
                           (url, ))
            db_web = cursor.fetchone()
        if db_web:
            website = Website(db_web[1], db_web[2], db_web[3], db_web[4], db_web[0])
            return website
        else:
            return None

    def get_website_by_id(self, website_id):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM Website WHERE id=?", (website_id, ))
            db_web = cursor.fetchone()

            if db_web:
                website = Website(db_web[1], db_web[2], db_web[3], db_web[4])
                website.id = db_web[0]
                return website
            else:
                return None

    def get_websites(self, per_page, page: int, url):
        """Get all websites"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT Website.id, Website.url, Website.last_modified FROM Website "
                           "WHERE Website.url LIKE ?"
                           "ORDER BY last_modified DESC LIMIT ? OFFSET ?", (url + "%", per_page, page * per_page))

            return cursor.fetchall()

    def get_random_website_id(self):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM Website WHERE id >= (abs(random()) % (SELECT max(id) FROM Website)) LIMIT 1;")

            return cursor.fetchone()[0]

    def website_exists(self, url):
        """Check if an url or the parent directory of an url already exists"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM Website WHERE url = substr(?, 0, length(url) + 1)", (url, ))
            website_id = cursor.fetchone()
            return website_id[0] if website_id else None

    def delete_website(self, website_id):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM Website WHERE id=?", (website_id, ))
            conn.commit()

    def check_login(self, username, password) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT password FROM Admin WHERE username=?", (username, ))

            db_user = cursor.fetchone()

            if db_user:
                return bcrypt.checkpw(password.encode(), db_user[0])
            return False

    def get_user_role(self, username: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT role FROM Admin WHERE username=?", (username, ))

            db_user = cursor.fetchone()

            if db_user:
                return db_user[0]
            return False

    def generate_login(self, username, password) -> None:

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12))

            cursor.execute("INSERT INTO Admin (username, password, role) VALUES (?,?, 'admin')", (username, hashed_pw))
            conn.commit()

    def check_api_token(self, token) -> str:

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM ApiClient WHERE token=?", (token, ))
            result = cursor.fetchone()
            return result[0] if result else None

    def generate_api_token(self, name: str) -> str:

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            token = str(uuid.uuid4())
            cursor.execute("INSERT INTO ApiClient (token, name) VALUES (?, ?)", (token, name))
            conn.commit()

            return token

    def get_tokens(self) -> list:

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT token, name FROM ApiClient")

            return [ApiClient(x[0], x[1]) for x in cursor.fetchall()]

    def delete_token(self, token: str) -> None:

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM ApiClient WHERE token=?", (token, ))
            conn.commit()

    def get_all_websites(self) -> dict:

        # todo: mem cache that
        with sqlite3.connect(self.db_path) as conn:

            cursor = conn.cursor()

            cursor.execute("SELECT id, url FROM Website")

            result = {}

            for db_website in cursor.fetchall():
                result[db_website[0]] = db_website[1]
            return result

    def join_website_on_search_result(self, page: dict) -> dict:

        websites = self.get_all_websites()

        for hit in page["hits"]["hits"]:
            if hit["_source"]["website_id"] in websites:
                hit["_source"]["website_url"] = websites[hit["_source"]["website_id"]]
            else:
                hit["_source"]["website_url"] = "[DELETED]"

        return page

    def join_website_on_scan(self, docs: list):

        websites = self.get_all_websites()

        for doc in docs:
            if doc["_source"]["website_id"] in websites:
                doc["_source"]["website_url"] = websites[doc["_source"]["website_id"]]
            else:
                doc["_source"]["website_url"] = "[DELETED]"

            yield doc

    def join_website_on_stats(self, stats):

        websites = self.get_all_websites()

        for website in stats["website_scatter"]:
                website[0] = websites.get(website[0], "[DELETED]")

    def add_blacklist_website(self, url):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            parsed_url = urlparse(url)
            url = parsed_url.scheme + "://" + parsed_url.netloc
            cursor.execute("INSERT INTO BlacklistedWebsite (url) VALUES (?)", (url, ))
            conn.commit()

    def remove_blacklist_website(self, blacklist_id):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM BlacklistedWebsite WHERE id=?", (blacklist_id, ))
            conn.commit()

    def is_blacklisted(self, url):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            parsed_url = urlparse(url)
            url = parsed_url.scheme + "://" + parsed_url.netloc
            print(url)
            cursor.execute("SELECT id FROM BlacklistedWebsite WHERE url LIKE ? LIMIT 1", (url, ))

            return cursor.fetchone() is not None

    def get_blacklist(self):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM BlacklistedWebsite")
            return [BlacklistedWebsite(r[0], r[1]) for r in cursor.fetchall()]

    def log_search(self, remote_addr, forwarded_for, q, exts, page, blocked, results, took):

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("INSERT INTO SearchLogEntry (remote_addr, forwarded_for, query, extensions, page, blocked, results, took) "
                           "VALUES (?,?,?,?,?,?,?,?)", (remote_addr, forwarded_for, q, ",".join(exts), page, blocked, results, took))

            conn.commit()
