
from code import interact
import logging
from os import getcwd, kill, remove
from os.path import dirname, join

from daemon import daemonize
from twitter import Api, TwitterError

from babbler.feed import Feed
from babbler.options import Options
from babbler.responder import RespondingFeed
from babbler.tagging import Tagger
from babbler.persistence import PersistentDict


TWEET_MAX_LEN = 140


class Bot(object):

    def __init__(self, version=None, description=None):
        """
        Handles command-line arg parsing and loading of data.
        """
        # Set up file paths.
        self.package_data_path = join(dirname(__file__), "data")
        self.data_path = join(getcwd(), "babbler.data")
        self.pid_path = join(getcwd(), "babbler.pid")
        self.log_path = join(getcwd(), "babbler.log")
        self.options_path = join(self.package_data_path, "options.yml")
        self.eliza_path = join(self.package_data_path, "eliza.yml")
        # Load persisted data.
        self.data = PersistentDict(path=self.data_path)
        existing_options = {}
        if self.data.load():
            existing_options = self.data["options"]
            # Migrate from 0.1 format.
            if "todo" in self.data:
                self.data["feed"] = RespondingFeed()
                self.data["feed"].todo = self.data.pop("todo")
                self.data["feed"].done = self.data.pop("done")
            # Migrate from 0.2 format.
            feed = self.data["feed"]
            if isinstance(feed, Feed):
                self.data["feed"] = RespondingFeed()
                self.data["feed"].todo = feed.todo
                self.data["feed"].done = feed.done
        else:
            print
            print "Initial setup. Data will be saved to '%s'" % self.data_path
            print
        # Load options.
        options = Options(self.options_path, existing=existing_options,
                          description=description, version=version)
        self.data["options"] = options.parse_args()
        self.data.save()
        # Set up the Twitter API object.
        api = Api(**dict([(k, v) for k, v in self.data["options"].items()
                          if k.split("_")[0] in ("consumer", "access")]))
        self.twitter = api

    def run(self, as_daemon=False):
        """
        Main event loop that gets the entries from the feed and posts them
        to Twitter.
        """
        # Set up logging.
        logger_args = {"format": "%(asctime)-15s %(levelname)-5s %(message)s"}
        if as_daemon:
            self.kill()
            daemonize(self.pid_path)
            logger_args.update({"filename": self.log_path, "filemode": "wb"})
        logging.basicConfig(**logger_args)
        log_level = getattr(logging, self.data["options"]["log_level"])
        logging.getLogger().setLevel(log_level)
        logging.debug("\n\nUsing options:\n\n%s\n" % self.data["options"])
        # Set up the feed.
        self.data.setdefault("feed", RespondingFeed())
        feed_options = dict(twitter=self.twitter, max_len=TWEET_MAX_LEN,
                            eliza_path=self.eliza_path, **self.data["options"])
        self.data["feed"].setup(feed_options)
        self.data.save()
        # Set up hashtagging.
        tagger = Tagger(scorer=self.hashtag_score,
                        data_path=self.package_data_path,
                        min_length=self.data["options"]["hashtag_min_length"])
        # Main loop.
        for entry in self.data["feed"]:
            try:
                # Twitter reply.
                tweet = "%s %s" % (entry["to"], entry["title"])
                reply_to = entry["id"]
            except KeyError:
                # Feed entry.
                tweet = entry["title"]
                reply_to = None
            for tag in tagger.tags(entry["title"]):
                tag = " #" + tag
                # Extra check to ensure tag isn't already in the tweet.
                if (len(tweet + tag) <= TWEET_MAX_LEN and
                    tag.strip().lower() not in tweet.lower()):
                    tweet += tag
            # Post to Twitter.
            done = True
            try:
                if not self.data["options"]["dry_run"]:
                    self.twitter.PostUpdate(tweet, reply_to)
            except TwitterError, e:
                logging.error("Twitter error: %s" % e)
                # Mark the entry as done if it's a duplicate.
                done = str(e) == "Status is a duplicate."
            if done:
                logging.info("Tweeted: %s" % tweet)
                # Move the entry from "todo" to "done" and save.
                self.data["feed"].process()
                if not self.data["options"]["dry_run"]:
                    self.data.save()

    def hashtag_score(self, hashtag):
        """
        Searchs Twitter for the given hashtag, and creates a score for
        it based on the age of each search result.
        """
        try:
            results = self.twitter.GetSearch("#" + hashtag)
        except TwitterError, e:
            logging.error("Twitter error: %s" % e)
        except UnicodeEncodeError:
            pass
        else:
            return sum([t.created_at_in_seconds for t in results])
        return 0

    def destroy(self):
        """
        Destroys persisted data file and deletes all tweets from Twitter
        when the --DESTROY option is given.
        """
        print
        print "WARNING: You have specified the --DESTROY option."
        print "All tweets will be deleted from your account."
        if raw_input("Enter 'y' to continue. ").strip().lower() == "y":
            print "Deleting all data and tweets."
            try:
                self.data.remove()
            except OSError:
                pass
            while True:
                tweets = self.twitter.GetUserTimeline()
                if not tweets:
                    break
                for tweet in tweets:
                    try:
                        self.twitter.DestroyStatus(tweet.id)
                    except TwitterError:
                        pass
            print "Done."
        else:
            print "--DESTROY aborted"

    def edit(self):
        """
        Runs a Python shell for editing the data file.
        """
        print
        print "All data is stored in the persisted dictionary named "
        print "'bot.data' which contains the follwing entries:"
        print
        print "All entry IDs that have either been posted or ignored:"
        print "bot.data['feed'].done = set()"
        print
        print "All entries that have been retrieved from the feed and "
        print "are waiting to be posted to Twitter. Each dict contains "
        print "'id' and 'title' keys:"
        print "bot.data['feed'].todo = []"
        print
        print "All options that have been persisted:"
        print "bot.data['options'] = {}"
        print
        print "Call the 'bot.data.save()' method to persist changes made."
        print
        interact(local={"bot": self})

    def kill(self):
        """
        Try to stop a previously started daemon.
        """
        try:
            with open(self.pid_path) as f:
                kill(int(f.read()), 9)
            remove(self.pid_path)
        except (IOError, OSError):
            return False
        return True
